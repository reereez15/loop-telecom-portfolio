"""멤버십 등급 직접 구매(업그레이드) — DB 테이블 없이 처리한다.

왜 테이블이 없나
  카카오페이는 ready 응답으로 tid 를 주지만, 결제창에서 돌아올 때(approval_url) 붙여주는 값은 pg_token 뿐이다.
  approval_url 은 ready 를 부를 때 미리 넘기는 값이라 그 시점에는 tid 를 모르므로 URL 에 실을 수도 없다.
  그래서 tid 를 ready~approve 사이에 어딘가 보관해야 하는데, 공용 DB 스키마를 바꾸지 않기 위해
  HttpOnly 쿠키에 담는다(구매 이력 테이블을 만들지 않는다).

조작이 안 되는 이유
  - 금액은 항상 서버가 tiers.UPGRADE_PRICES 로 다시 계산한다. 요청 본문의 금액은 받지 않는다.
  - 주문번호를 "upg-{user_id}-{rank}" 로 정해두고 approve 때 세션의 user_id 와 쿠키의 rank 로 서버가 다시 만든다.
    쿠키를 고쳐 더 비싼 등급을 받으려 해도 카카오페이가 보관한 주문번호와 달라 승인이 거절된다.
  - 승인 응답의 amount.total 과 서버가 계산한 가격이 다르면 즉시 결제를 취소한다.
  - 등급 반영은 "구매 시작 시점 등급과 지금 등급이 같을 때만" 조건부 UPDATE 한다. 그사이 관리자가 바꿨거나
    다른 창에서 이미 올렸으면 반영하지 않고 카카오페이 결제도 취소한다.

한계(테이블을 두지 않아 생기는 것)
  - 구매 이력이 남지 않는다 → 관리자 구매 내역 조회 화면이 없다. 결제 사실은 카카오페이 쪽에만 남는다.
  - 브라우저가 쿠키를 지우면 승인을 이어갈 수 없다(결제는 승인 전이라 돈이 빠지지 않는다).
"""
import json
import re

from flask import Blueprint, request

from ..core.errors import ApiError, validation_error
from ..core.logging import app_log, security_event
from ..core.permissions import current_user, login_required
from ..core.responses import ok
from ..core.validation import body
from ..extensions import db
from ..models import MembershipAccount, MembershipTier
from . import service
from .tiers import customer_rank, tier_name, upgrade_price
from ..payments import gateway, kakaopay

bp = Blueprint("membership_upgrade", __name__, url_prefix="/api/membership/upgrade")

PG_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")
PENDING_COOKIE = "telecom_upgrade_pending"   # 카카오페이 ready~approve 사이에만 쓰는 임시 쿠키


def _order_id(user_id: int, rank: int) -> str:
    """카카오페이에 넘기는 주문번호. approve 때 서버가 같은 규칙으로 다시 만들어 대조한다."""
    return f"upg-{user_id}-{rank}"


def _target_tier(account: MembershipAccount, rank) -> MembershipTier:
    if isinstance(rank, bool) or not isinstance(rank, int) or rank not in (1, 2):
        raise validation_error({"tier_rank": "업그레이드할 등급은 1(Plus) 또는 2(VIP)여야 합니다."})
    tier = MembershipTier.query.filter_by(rank=rank).first()
    if tier is None:
        raise ApiError("NOT_READY", "멤버십 등급 정보가 없습니다.", 503)
    if customer_rank(tier.rank) <= customer_rank(account.tier.rank):
        raise ApiError("ALREADY_AT_OR_ABOVE", "이미 그 등급 이상입니다.", 409)
    return tier


def _locked_account(user_id: int) -> MembershipAccount:
    account = service.locked_account(user_id)
    if account is None:
        raise ApiError("NOT_MEMBER", "L∞P+ 멤버십에 먼저 가입하세요.", 403)
    return account


def _claim_tier(account: MembershipAccount, from_tier_id: int, to_tier_id: int) -> bool:
    """지금 등급이 구매 시작 시점과 같을 때만 반영. 그사이 바뀌었으면 False."""
    from sqlalchemy import update
    claimed = db.session.execute(
        update(MembershipAccount).where(MembershipAccount.id == account.id,
                                        MembershipAccount.tier_id == from_tier_id)
        .values(tier_id=to_tier_id)
    ).rowcount
    return claimed == 1


def _result(tier: MembershipTier, amount: int, method: str) -> dict:
    return {"to_tier_rank": customer_rank(tier.rank), "to_tier_name": tier_name(tier),
            "amount": amount, "method": method}


# ---------- 모의 카드 (한 요청 안에서 끝나므로 보관할 상태가 없다) ----------

@bp.post("")
@login_required
def purchase_mock():
    user = current_user()
    data = body()
    account = _locked_account(user.id)
    to_tier = _target_tier(account, data.get("tier_rank"))
    amount = upgrade_price(to_tier)

    result = gateway.charge(data.get("card_number"), amount)
    if not result.approved:
        db.session.rollback()
        app_log("membership.upgrade.declined", user_id=user.id, to_rank=to_tier.rank)
        return ok({"approved": False, "upgrade": None}, 200)

    if not _claim_tier(account, account.tier_id, to_tier.id):
        db.session.rollback()
        raise ApiError("CONFLICT", "그사이 등급이 바뀌었습니다. 다시 시도하세요.", 409)
    db.session.commit()
    app_log("membership.upgrade.succeeded", user_id=user.id, to_rank=to_tier.rank,
            transaction_ref=result.transaction_ref)
    return ok({"approved": True,
               "upgrade": {**_result(to_tier, amount, "MOCK_CARD"),
                           "transaction_ref": result.transaction_ref}}, 201)


# ---------- 카카오페이 테스트 결제 ----------

@bp.post("/kakaopay/ready")
@login_required
def kakaopay_ready():
    user = current_user()
    if not kakaopay.enabled():
        raise ApiError("PG_DISABLED", "카카오페이 테스트 결제가 설정되지 않았습니다.", 503)
    account = _locked_account(user.id)
    to_tier = _target_tier(account, body().get("tier_rank"))
    rank, amount = customer_rank(to_tier.rank), upgrade_price(to_tier)

    try:
        res = kakaopay.ready(_order_id(user.id, rank), user.id, f"L∞P+ {tier_name(to_tier)} 등급 구매",
                             amount, section="membership", return_query=f"rank={rank}")
    except kakaopay.KakaoPayError as err:
        raise ApiError("PG_ERROR", f"카카오페이 결제 준비에 실패했습니다: {err}", 502)

    tid = str(res.get("tid") or "")
    redirect = res.get("next_redirect_pc_url") or res.get("next_redirect_mobile_url")
    if not tid or not redirect:
        raise ApiError("PG_ERROR", "카카오페이 응답이 올바르지 않습니다.", 502)

    resp, status = ok({"redirect_url": redirect, "amount": amount}, 201)
    # tid 는 브라우저 스크립트가 읽지 못하도록 HttpOnly 로 두고, 승인 때 자동으로 되돌아오게 한다
    resp.set_cookie(PENDING_COOKIE, json.dumps({"tid": tid, "rank": rank}),
                    max_age=1800, httponly=True, secure=True, samesite="Lax", path="/")
    app_log("membership.upgrade.kakaopay.ready", user_id=user.id, to_rank=rank)
    return resp, status


def _pending():
    try:
        data = json.loads(request.cookies.get(PENDING_COOKIE) or "{}")
        tid, rank = str(data.get("tid") or ""), data.get("rank")
    except ValueError:
        tid, rank = "", None
    if not tid or rank not in (1, 2):
        raise ApiError("NO_PENDING_PAYMENT", "진행 중인 카카오페이 결제를 찾을 수 없습니다. 다시 시도해 주세요.", 409)
    return tid, rank


def _clear(resp):
    resp.delete_cookie(PENDING_COOKIE, path="/")
    return resp


@bp.post("/kakaopay/approve")
@login_required
def kakaopay_approve():
    user = current_user()
    pg_token = str(body().get("pg_token") or "")
    if not PG_TOKEN_RE.match(pg_token):
        raise validation_error({"pg_token": "pg_token 형식이 올바르지 않습니다."})
    tid, rank = _pending()

    account = _locked_account(user.id)
    to_tier = MembershipTier.query.filter_by(rank=rank).first()
    if to_tier is None:
        raise ApiError("NOT_READY", "멤버십 등급 정보가 없습니다.", 503)
    amount = upgrade_price(to_tier)

    try:
        # 주문번호는 세션의 user_id 와 쿠키의 rank 로 서버가 다시 만든다 → 조작 시 카카오페이가 거절한다
        res = kakaopay.approve(tid, _order_id(user.id, rank), user.id, pg_token)
    except kakaopay.KakaoPayError as err:
        raise ApiError("PG_ERROR", f"카카오페이 승인에 실패했습니다: {err}", 502)

    approved_total = (res.get("amount") or {}).get("total")
    if approved_total != amount:
        security_event("payment.validation.failed", "high", "카카오페이 승인 금액 불일치(멤버십 등급 구매)",
                       user_id=user.id, approved_amount=approved_total, expected_amount=amount)
        try:
            kakaopay.cancel(tid, approved_total or amount)
        except kakaopay.KakaoPayError:
            pass
        raise ApiError("AMOUNT_MISMATCH", "승인 금액이 구매 금액과 달라 결제를 취소했습니다.", 422)

    if customer_rank(account.tier.rank) >= customer_rank(to_tier.rank) \
            or not _claim_tier(account, account.tier_id, to_tier.id):
        db.session.rollback()
        try:
            kakaopay.cancel(tid, amount)
        except kakaopay.KakaoPayError:
            pass
        security_event("payment.duplicate_request", "medium", "그사이 등급이 바뀐 상태로 카카오페이 승인 시도",
                       user_id=user.id, to_rank=rank)
        raise ApiError("CONFLICT", "그사이 등급이 바뀌어 카카오페이 결제는 취소했습니다.", 409)

    db.session.commit()
    app_log("membership.upgrade.kakaopay.approved", user_id=user.id, to_rank=rank)
    resp, status = ok({"upgrade": _result(to_tier, amount, "KAKAOPAY")})
    return _clear(resp), status


@bp.post("/kakaopay/abort")
@login_required
def kakaopay_abort():
    """사용자가 결제창에서 취소하거나 실패하고 돌아온 경우. 승인 전이라 서버가 정리할 것은 쿠키뿐이다."""
    resp, status = ok({"aborted": True})
    return _clear(resp), status
