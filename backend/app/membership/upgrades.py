"""KakaoPay tier purchases using existing security_audit_logs only.
Purchase and redirect rows are durable business records: retain them for reconciliation.
No migrations, invoice fabrication, role changes or point deductions.
"""
import json
import re
from urllib.parse import urlsplit

from flask import current_app
from ..core.errors import ApiError, validation_error
from ..core.permissions import current_user, login_required
from ..core.responses import ok
from ..core.validation import body, idempotency_key, idempotency_conflict, request_hash
from ..extensions import db
from ..models import MembershipTier, SecurityAuditLog
from ..payments import kakaopay
from .service import locked_account
from .tiers import customer_rank
from .routes import bp

PRODUCTS = {1: ('Plus', 14900), 2: ('VIP', 29900)}
ACTION = 'membership.purchase'
ACTIVE = ('PREPARING', 'PENDING', 'APPROVING', 'REVIEW', 'REFUND_REQUIRED')


def ledger(user):
    return SecurityAuditLog.query.filter_by(action=ACTION, actor_id=user.id)


def lock(user):
    if user.role != 'CUSTOMER':
        raise ApiError('FORBIDDEN', '고객 계정에서만 구매할 수 있습니다.', 403)
    account = locked_account(user.id)
    if account is None:
        raise ApiError('NOT_MEMBER', '먼저 무료 멤버십에 가입하세요.', 409)
    return account


def info(row):
    return json.loads(row.target)


def view(row):
    d = info(row)
    return {'id': row.id, 'rank': d['rank'], 'name': PRODUCTS[d['rank']][0],
            'amount': d['amount'], 'status': row.result, 'duration': 'permanent'}


def redirects(row):
    chunks = SecurityAuditLog.query.filter_by(action='membership.redirect', actor_id=row.actor_id,
                                              workflow=str(row.id)).order_by(SecurityAuditLog.id).all()
    return ''.join(x.target for x in chunks)


def find(user, order_id):
    if type(order_id) is not int:
        raise validation_error({'purchase_id': '구매 ID가 필요합니다.'})
    row = ledger(user).filter_by(id=order_id).with_for_update().first()
    if row is None:
        raise ApiError('NOT_FOUND', '구매 내역을 찾을 수 없습니다.', 404)
    return row


def urls(order_id):
    base = current_app.config['PUBLIC_BASE_URL'].rstrip('/')
    return {key: f'{base}/membership/kakaopay/{phase}?purchase_id={order_id}'
            for key, phase in [('approval_url', 'approve'), ('cancel_url', 'cancel'), ('fail_url', 'fail')]}


def fail(message, code='PURCHASE_REVIEW', status=409):
    raise ApiError(code, message, status)


@bp.get('/upgrades/me')
@login_required
def purchases():
    return ok({'purchases': [view(x) for x in ledger(current_user()).order_by(SecurityAuditLog.id.desc()).limit(30)]})


@bp.post('/upgrades/kakaopay/ready')
@login_required
def ready():
    user, data, key = current_user(), body(), idempotency_key()
    account = lock(user)
    rank = data.get('rank')
    if type(rank) is not int or rank not in PRODUCTS:
        raise validation_error({'rank': 'Plus 또는 VIP를 선택하세요.'})
    fingerprint = request_hash('membership.kakaopay', {'rank': rank})
    old = ledger(user).filter_by(workflow=key).with_for_update().first()
    if old:
        if old.reason != fingerprint:
            raise idempotency_conflict()
        if old.result not in ('PENDING', 'SUCCEEDED'):
            fail('이전 결제 결과를 확인해야 합니다. 구매 내역을 확인하거나 관리자에게 문의하세요.')
        return ok({'purchase': view(old), 'redirect_url': redirects(old) if old.result == 'PENDING' else None})
    if ledger(user).filter(SecurityAuditLog.result.in_(ACTIVE)).with_for_update().first():
        fail('진행 중인 결제가 있습니다. 기존 결제를 이어서 진행하거나 취소하세요.')
    if customer_rank(account.tier.rank) >= rank:
        fail('현재 등급보다 높은 등급만 구매할 수 있습니다.')
    tier = MembershipTier.query.filter_by(rank=rank).first()
    if not tier:
        fail('멤버십 등급 설정을 확인하세요.', 'NOT_READY', 503)
    if not kakaopay.enabled():
        fail('카카오페이가 설정되지 않았습니다.', 'PG_DISABLED', 503)
    name, amount = PRODUCTS[rank]
    row = SecurityAuditLog(actor_type='SYSTEM', actor_id=user.id, action=ACTION, workflow=key,
                           target_type='membership', target=json.dumps({'rank': rank, 'tier_id': tier.id, 'amount': amount}),
                           result='PREPARING', reason=fingerprint)
    db.session.add(row)
    db.session.commit()  # Persist before external call; unresolved ready never silently retried.
    try:
        res = kakaopay.ready(f'membership-{row.id}', user.id, f'L∞P {name} 영구 멤버십', amount, return_urls=urls(row.id))
        if not isinstance(res, dict):
            raise ValueError('Invalid ready response')
        tid, redirect = res.get('tid'), res.get('next_redirect_pc_url') or res.get('next_redirect_mobile_url')
        parsed = urlsplit(redirect or '')
        if not isinstance(tid, str) or not 1 <= len(tid) <= 64 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or len(redirect) > 2048:
            raise ValueError('Invalid ready response')
        d = info(row); d['tid'] = tid
        row.target, row.result = json.dumps(d), 'PENDING'
        for start in range(0, len(redirect), 255):
            db.session.add(SecurityAuditLog(actor_type='SYSTEM', actor_id=user.id, workflow=str(row.id),
                action='membership.redirect', target_type='membership', target=redirect[start:start+255], result='DONE'))
        db.session.commit()
    except (kakaopay.KakaoPayError, ValueError, TypeError):
        db.session.rollback()
        row.result = 'REVIEW'; db.session.commit()
        fail('결제 준비 결과를 확인할 수 없습니다. 관리자 확인 후 다시 진행하세요.', status=502)
    return ok({'purchase': view(row), 'redirect_url': redirect}, 201)


@bp.post('/upgrades/kakaopay/resume')
@login_required
def resume():
    user = current_user(); lock(user)
    row = find(user, body().get('purchase_id'))
    if row.result != 'PENDING':
        fail('결제를 이어서 진행할 수 없는 상태입니다.')
    return ok({'purchase': view(row), 'redirect_url': redirects(row)})


@bp.post('/upgrades/kakaopay/abort')
@login_required
def abort():
    user = current_user(); lock(user)
    row = find(user, body().get('purchase_id'))
    if row.result == 'PENDING':
        row.result = 'CANCELED'; db.session.commit()
    elif row.result != 'CANCELED':
        fail('결제 결과 확인이 필요한 상태입니다. 관리자에게 문의하세요.')
    return ok({'purchase': view(row)})


@bp.post('/upgrades/kakaopay/approve')
@login_required
def approve():
    user, data = current_user(), body()
    account = lock(user)
    row = find(user, data.get('purchase_id'))
    if row.result == 'SUCCEEDED':
        return ok({'purchase': view(row)})
    token = data.get('pg_token')
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9]{1,64}', token):
        raise validation_error({'pg_token': '결제 인증 토큰이 올바르지 않습니다.'})
    if row.result != 'PENDING':
        fail('이미 처리 중이거나 확인이 필요한 결제입니다.')
    d = info(row)
    if customer_rank(account.tier.rank) >= d['rank']:
        row.result = 'CANCELED'; db.session.commit()
        fail('현재 등급이 이미 변경되어 결제를 승인하지 않았습니다.')
    row.result = 'APPROVING'; db.session.commit()  # Other requests cannot approve the same order.
    try:
        res = kakaopay.approve(d['tid'], f'membership-{row.id}', user.id, token)
    except (kakaopay.KakaoPayError, ValueError, TypeError):
        row.result = 'REVIEW'; db.session.commit()
        fail('승인 결과를 확인할 수 없습니다. 재결제하지 말고 관리자에게 문의하세요.', status=502)
    amount = res.get('amount', {}).get('total') if isinstance(res, dict) and isinstance(res.get('amount'), dict) else None
    valid = (type(amount) is int and amount == d['amount'] and res.get('tid') == d['tid']
             and str(res.get('partner_order_id')) == f'membership-{row.id}'
             and str(res.get('partner_user_id')) == str(user.id))
    if not valid:
        row.result = 'REFUND_REQUIRED'
        try:
            canceled = kakaopay.cancel(d['tid'], amount if type(amount) is int and amount > 0 else d['amount'])
            if canceled.get('status') == 'CANCEL_PAYMENT':
                row.result = 'CANCELED'
        except (kakaopay.KakaoPayError, ValueError, TypeError):
            pass
        db.session.commit()
        fail('승인 정보가 일치하지 않아 등급을 변경하지 않았습니다. 구매 내역을 확인하세요.', 'PG_MISMATCH', 422)
    try:
        account = lock(user)
        row = find(user, row.id)
        # Concurrent administrative upgrades must never be downgraded.
        if customer_rank(account.tier.rank) < d['rank']:
            account.tier_id = d['tier_id']
        row.result = 'SUCCEEDED'
        db.session.commit()
    except Exception:
        db.session.rollback()
        row.result = 'REVIEW'; db.session.commit()
        fail('결제는 승인되었으나 등급 반영 확인이 필요합니다. 재결제하지 말고 관리자에게 문의하세요.', status=503)
    return ok({'purchase': view(row)})
