"""멤버십 등급 직접 구매(업그레이드) — docs/contracts/membership-api.md 확장.

- 가격: MembershipTier.min_monthly_fee 를 1회성 구매 가격으로 그대로 쓴다(별도 가격 컬럼 없음, tiers.py tier_dict 의 "price")
- 결제(payments) 모듈과 같은 방어: 서버가 가격을 다시 계산(요청 금액은 참고만), (user_id, idempotency_key) 멱등,
  같은 키·다른 내용은 409, 카카오페이 승인 금액이 서버 가격과 다르면 즉시 취소
- 동시성: 계정 행을 잠그고(SELECT ... FOR UPDATE) "지금 등급이 구매 시작 시점 등급과 같을 때만" 조건부 UPDATE로 반영
  (그사이 관리자가 등급을 바꿨거나 다른 채널로 이미 업그레이드했으면 거절하고, 카카오페이는 결제를 취소한다)
- 환불은 아직 없음(등급을 환불로 되돌리는 정책이 아직 없어 관리자 환불 API는 만들지 않았다)
"""
import re

from flask import Blueprint
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..core.errors import ApiError, validation_error
from ..core.logging import app_log, security_event
from ..core.permissions import ROLE_ADMIN, current_user, login_required, roles_required
from ..core.responses import ok
from ..core.validation import body, idempotency_conflict, idempotency_key, request_hash
from ..extensions import db
from ..models import MembershipAccount, MembershipTier, MembershipUpgrade, User
from . import service
from .tiers import customer_rank, tier_name
from ..payments import gateway, kakaopay

bp = Blueprint("membership_upgrade", __name__, url_prefix="/api/membership/upgrade")
admin_bp = Blueprint("membership_upgrade_admin", __name__, url_prefix="/api/admin/membership/upgrades")

PG_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")


def _price(tier: MembershipTier) -> int:
    return tier.min_monthly_fee


def upgrade_dict(u: MembershipUpgrade, with_events=False) -> dict:
    data = u.to_dict()
    from_tier = db.session.get(MembershipTier, u.from_tier_id)
    to_tier = db.session.get(MembershipTier, u.to_tier_id)
    data["from_tier_name"] = tier_name(from_tier) if from_tier else None
    data["to_tier_name"] = tier_name(to_tier) if to_tier else None
    data["to_tier_rank"] = customer_rank(to_tier.rank) if to_tier else None
    return data


def _target_tier(account: MembershipAccount, data: dict) -> MembershipTier:
    rank = data.get("tier_rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank not in (1, 2):
        raise validation_error({"tier_rank": "업그레이드할 등급은 1(Plus) 또는 2(VIP)여야 합니다."})
    tier = MembershipTier.query.filter_by(rank=rank).first()
    if tier is None:
        raise ApiError("NOT_READY", "멤버십 등급 정보가 없습니다.", 503)
    if customer_rank(tier.rank) <= customer_rank(account.tier.rank):
        raise ApiError("ALREADY_AT_OR_ABOVE", "이미 그 등급 이상입니다.", 409)
    return tier


def _claim_tier(account: MembershipAccount, from_tier_id: int, to_tier_id: int) -> bool:
    """지금 등급이 구매 시작 시점과 같을 때만 반영. 그사이 바뀌었으면 False."""
    claimed = db.session.execute(
        update(MembershipAccount).where(MembershipAccount.id == account.id,
                                        MembershipAccount.tier_id == from_tier_id)
        .values(tier_id=to_tier_id)
    ).rowcount
    return claimed == 1


# ---------- 조회 ----------
# 가격·구매 가능 여부는 /api/membership/me, /api/membership/tiers 의 tier_dict(price 포함)로 이미 내려간다.
# 프런트엔드가 쓰지 않는 별도 "/options" 엔드포인트는 두지 않는다.

@bp.get("/me")
@login_required
def my_upgrades():
    rows = (MembershipUpgrade.query.filter_by(user_id=current_user().id)
            .order_by(MembershipUpgrade.id.desc()).limit(20).all())
    return ok({"upgrades": [upgrade_dict(u) for u in rows]})


# ---------- 모의 카드 ----------

@bp.post("")
@login_required
def purchase_mock():
    user = current_user()
    key = idempotency_key()
    data = body()
    req_hash = request_hash("membership.upgrade.create",
                            {"tier_rank": data.get("tier_rank"), "card_number": data.get("card_number")})
    replay = MembershipUpgrade.query.filter_by(user_id=user.id, idempotency_key=key).first()
    if replay:
        if replay.request_hash != req_hash:
            raise idempotency_conflict()
        return ok({"upgrade": upgrade_dict(replay), "replayed": True})

    account = service.locked_account(user.id)
    if account is None:
        raise ApiError("NOT_MEMBER", "L∞P+ 멤버십에 먼저 가입하세요.", 403)
    to_tier = _target_tier(account, data)
    amount = _price(to_tier)

    purchase = MembershipUpgrade(user_id=user.id, from_tier_id=account.tier_id, to_tier_id=to_tier.id,
                                 amount=amount, idempotency_key=key, request_hash=req_hash,
                                 transaction_ref=f"PENDING-{user.id}-{key}"[:64], status="PENDING")
    db.session.add(purchase)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        again = MembershipUpgrade.query.filter_by(user_id=user.id, idempotency_key=key).one()
        if again.request_hash != req_hash:
            raise idempotency_conflict()
        return ok({"upgrade": upgrade_dict(again), "replayed": True})

    result = gateway.charge(data.get("card_number"), amount)
    purchase.transaction_ref = result.transaction_ref
    purchase.method = f"MOCK_CARD_{result.card_last4}" if result.card_last4 else "MOCK_CARD"

    if not result.approved:
        purchase.status = "FAILED"
        db.session.commit()
        app_log("membership.upgrade.declined", user_id=user.id, upgrade_id=purchase.id)
        return ok({"upgrade": upgrade_dict(purchase), "replayed": False}, 201)

    if not _claim_tier(account, purchase.from_tier_id, to_tier.id):
        purchase.status = "CANCELED"
        db.session.commit()
        security_event("payment.duplicate_request", "medium", "그사이 등급이 바뀐 상태로 업그레이드 결제 시도",
                       user_id=user.id, upgrade_id=purchase.id)
        raise ApiError("CONFLICT", "그사이 등급이 바뀌어 결제를 취소했습니다. 다시 시도하세요.", 409)

    purchase.status = "SUCCEEDED"
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("CONFLICT", "그사이 등급이 바뀌어 결제를 취소했습니다. 다시 시도하세요.", 409)
    app_log("membership.upgrade.succeeded", user_id=user.id, upgrade_id=purchase.id, to_rank=to_tier.rank)
    return ok({"upgrade": upgrade_dict(purchase)}, 201)


# ---------- 카카오페이 테스트 결제 ----------

def _my_kakao_upgrade(user, upgrade_id):
    if not isinstance(upgrade_id, int) or isinstance(upgrade_id, bool):
        raise validation_error({"upgrade_id": "구매 ID가 필요합니다."})
    purchase = MembershipUpgrade.query.filter_by(id=upgrade_id).with_for_update().first()
    if purchase is None or purchase.user_id != user.id or purchase.method != "KAKAOPAY":
        raise ApiError("NOT_FOUND", "구매 내역을 찾을 수 없습니다.", 404)
    return purchase


@bp.post("/kakaopay/ready")
@login_required
def kakaopay_ready():
    user = current_user()
    key = idempotency_key()
    data = body()
    if not kakaopay.enabled():
        raise ApiError("PG_DISABLED", "카카오페이 테스트 결제가 설정되지 않았습니다.", 503)
    req_hash = request_hash("membership.upgrade.kakaopay.ready", {"tier_rank": data.get("tier_rank")})
    replay = MembershipUpgrade.query.filter_by(user_id=user.id, idempotency_key=key).first()
    if replay:
        if replay.request_hash != req_hash:
            raise idempotency_conflict()
        return ok({"upgrade": upgrade_dict(replay), "redirect_url": None, "replayed": True})

    account = service.locked_account(user.id)
    if account is None:
        raise ApiError("NOT_MEMBER", "L∞P+ 멤버십에 먼저 가입하세요.", 403)
    to_tier = _target_tier(account, data)
    amount = _price(to_tier)

    purchase = MembershipUpgrade(user_id=user.id, from_tier_id=account.tier_id, to_tier_id=to_tier.id,
                                 amount=amount, idempotency_key=key, request_hash=req_hash,
                                 transaction_ref=f"KAKAO-PENDING-{user.id}-{key}"[:64],
                                 method="KAKAOPAY", status="PENDING")
    db.session.add(purchase)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise idempotency_conflict()
    try:
        res = kakaopay.ready(purchase.id, user.id, f"L∞P+ {tier_name(to_tier)} 등급 구매", amount, section="membership")
    except kakaopay.KakaoPayError as err:
        purchase.status = "FAILED"
        db.session.commit()
        raise ApiError("PG_ERROR", f"카카오페이 결제 준비에 실패했습니다: {err}", 502)
    tid = str(res.get("tid") or "")
    redirect = res.get("next_redirect_pc_url") or res.get("next_redirect_mobile_url")
    if not tid or not redirect:
        purchase.status = "FAILED"
        db.session.commit()
        raise ApiError("PG_ERROR", "카카오페이 응답이 올바르지 않습니다.", 502)
    purchase.pg_tid = tid[:64]
    purchase.transaction_ref = f"KAKAO-{tid}"[:64]
    db.session.commit()
    app_log("membership.upgrade.kakaopay.ready", user_id=user.id, upgrade_id=purchase.id)
    return ok({"upgrade": upgrade_dict(purchase), "redirect_url": redirect, "replayed": False}, 201)


@bp.post("/kakaopay/approve")
@login_required
def kakaopay_approve():
    user = current_user()
    data = body()
    purchase = _my_kakao_upgrade(user, data.get("upgrade_id"))
    pg_token = str(data.get("pg_token") or "")
    if not PG_TOKEN_RE.match(pg_token):
        raise validation_error({"pg_token": "pg_token 형식이 올바르지 않습니다."})
    if purchase.status == "SUCCEEDED":
        return ok({"upgrade": upgrade_dict(purchase)})
    if purchase.status != "PENDING" or not purchase.pg_tid:
        raise ApiError("CONFLICT", "승인할 수 없는 결제 상태입니다.", 409)

    account = service.locked_account(user.id)
    try:
        res = kakaopay.approve(purchase.pg_tid, purchase.id, user.id, pg_token)
    except kakaopay.KakaoPayError as err:
        purchase.status = "FAILED"
        db.session.commit()
        raise ApiError("PG_ERROR", f"카카오페이 승인에 실패했습니다: {err}", 502)

    approved_total = (res.get("amount") or {}).get("total")
    if approved_total != purchase.amount:
        security_event("payment.validation.failed", "high", "카카오페이 승인 금액 불일치(멤버십 업그레이드)",
                       user_id=user.id, upgrade_id=purchase.id, approved_amount=approved_total,
                       expected_amount=purchase.amount)
        try:
            kakaopay.cancel(purchase.pg_tid, approved_total or purchase.amount)
        except kakaopay.KakaoPayError:
            pass
        purchase.status = "FAILED"
        db.session.commit()
        raise ApiError("AMOUNT_MISMATCH", "승인 금액이 구매 금액과 달라 결제를 취소했습니다.", 422)

    if account is None or not _claim_tier(account, purchase.from_tier_id, purchase.to_tier_id):
        try:
            kakaopay.cancel(purchase.pg_tid, purchase.amount)
        except kakaopay.KakaoPayError:
            pass
        purchase.status = "CANCELED"
        db.session.commit()
        security_event("payment.duplicate_request", "medium", "그사이 등급이 바뀐 상태로 카카오페이 승인 시도",
                       user_id=user.id, upgrade_id=purchase.id)
        raise ApiError("CONFLICT", "그사이 등급이 바뀌어 카카오페이 결제는 취소했습니다. 다시 시도하세요.", 409)

    purchase.status = "SUCCEEDED"
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("CONFLICT", "그사이 등급이 바뀌었습니다.", 409)
    app_log("membership.upgrade.kakaopay.approved", user_id=user.id, upgrade_id=purchase.id)
    return ok({"upgrade": upgrade_dict(purchase)})


@bp.post("/kakaopay/abort")
@login_required
def kakaopay_abort():
    user = current_user()
    data = body()
    purchase = _my_kakao_upgrade(user, data.get("upgrade_id"))
    reason = "CANCELED" if data.get("reason") == "cancel" else "FAILED"
    if purchase.status == "PENDING":
        purchase.status = reason
        db.session.commit()
    return ok({"upgrade": upgrade_dict(purchase)})


# ---------- 관리자: 구매 내역 조회 ----------

@admin_bp.get("")
@roles_required(ROLE_ADMIN)
def admin_upgrades():
    rows = MembershipUpgrade.query.order_by(MembershipUpgrade.id.desc()).limit(100).all()
    out = []
    for u in rows:
        d = upgrade_dict(u)
        d["customer_name"] = db.session.get(User, u.user_id).name
        out.append(d)
    return ok({"upgrades": out})
