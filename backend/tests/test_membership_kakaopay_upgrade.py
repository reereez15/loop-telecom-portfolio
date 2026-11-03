import uuid
import pytest
from app.extensions import db
from app.models import User, MembershipAccount, MembershipTier, SecurityAuditLog, Invoice, PointTransaction
from app.payments import kakaopay
from tests.conftest import csrf, login, logout

@pytest.fixture
def member(client):
    login(client,'alice@test.local')
    uid=User.query.filter_by(email='alice@test.local').one().id
    account=MembershipAccount.query.filter_by(user_id=uid).first()
    tier=MembershipTier.query.filter_by(rank=0).one()
    if not account:
        account=MembershipAccount(user_id=uid,tier_id=tier.id,point_balance=100);db.session.add(account)
    else: account.tier_id=tier.id
    db.session.commit()
    return account

@pytest.fixture
def pg(monkeypatch):
    calls=[]
    def fake(path,payload):
        calls.append((path,payload))
        if path.endswith('/ready'):return {'tid':'T123','next_redirect_pc_url':'https://online-pay.kakao.com/'+'x'*300}
        if path.endswith('/approve'):return {'tid':payload['tid'],'partner_order_id':payload['partner_order_id'],'partner_user_id':payload['partner_user_id'],'amount':{'total':fake.amount}}
        return {'status':'CANCEL_PAYMENT'}
    fake.amount=14900
    monkeypatch.setattr(kakaopay,'_post',fake)
    return fake,calls

def ready(client,rank=1,key=None):
    return client.post('/api/membership/upgrades/kakaopay/ready',json={'rank':rank,'amount':1},headers=csrf(client,**{'Idempotency-Key':key or str(uuid.uuid4())}))

def approve(client,pid):
    return client.post('/api/membership/upgrades/kakaopay/approve',json={'purchase_id':pid,'pg_token':'abc123'},headers=csrf(client))

@pytest.mark.parametrize('rank,amount',[(1,14900),(2,29900)])
def test_approved_only_and_replays(client,member,pg,rank,amount):
    fake,calls=pg;fake.amount=amount
    counts=(Invoice.query.count(),PointTransaction.query.count());balance=member.point_balance
    key=str(uuid.uuid4());res=ready(client,rank,key)
    assert res.status_code==201
    data=res.json['data'];pid=data['purchase']['id']
    assert calls[0][1]['total_amount']==amount
    assert '/membership/kakaopay/approve?' in calls[0][1]['approval_url']
    db.session.refresh(member);assert member.tier.rank==0
    assert ready(client,rank,key).json['data']['redirect_url']==data['redirect_url']
    assert len(calls)==1
    assert ready(client,3-rank,key).status_code==409
    assert ready(client,rank).status_code==409
    assert approve(client,pid).status_code==200
    db.session.refresh(member);assert member.tier.rank==rank and member.point_balance==balance
    assert (Invoice.query.count(),PointTransaction.query.count())==counts
    assert approve(client,pid).status_code==200 and len(calls)==2
    assert ready(client,rank).status_code==409

def test_owner_csrf_cancel(client,member,pg):
    assert client.post('/api/membership/upgrades/kakaopay/ready',json={'rank':1}).status_code==403
    pid=ready(client).json['data']['purchase']['id']
    logout(client);login(client,'bob@test.local');client.post('/api/membership/join',headers=csrf(client))
    assert approve(client,pid).status_code==404
    logout(client);login(client,'alice@test.local')
    assert client.post('/api/membership/upgrades/kakaopay/abort',json={'purchase_id':pid},headers=csrf(client)).status_code==200
    assert approve(client,pid).status_code==409
    db.session.refresh(member);assert member.tier.rank==0

def test_mismatch_no_upgrade(client,member,pg):
    fake,calls=pg;fake.amount=1
    pid=ready(client).json['data']['purchase']['id']
    assert approve(client,pid).status_code==422
    assert calls[-1][0].endswith('/cancel')
    assert db.session.get(SecurityAuditLog,pid).result=='CANCELED'
    db.session.refresh(member);assert member.tier.rank==0

def test_uncertain_approval_blocks_recharge(client,member,pg,monkeypatch):
    pid=ready(client).json['data']['purchase']['id']
    def fail(*a,**kw):raise kakaopay.KakaoPayError('timeout')
    monkeypatch.setattr(kakaopay,'approve',fail)
    assert approve(client,pid).status_code==502
    assert db.session.get(SecurityAuditLog,pid).result=='REVIEW'
    assert ready(client).status_code==409
    assert client.post('/api/membership/upgrades/kakaopay/abort',json={'purchase_id':pid},headers=csrf(client)).status_code==409
    db.session.refresh(member);assert member.tier.rank==0

@pytest.mark.parametrize('field', ['tid','partner_order_id','partner_user_id'])
def test_approval_identity_must_match(client,member,pg,monkeypatch,field):
    fake,calls=pg
    pid=ready(client).json['data']['purchase']['id']
    def mismatch(*args):
        result={'tid':'T123','partner_order_id':f'membership-{pid}','partner_user_id':str(member.user_id),'amount':{'total':14900}}
        result[field]='wrong'
        return result
    monkeypatch.setattr(kakaopay,'approve',mismatch)
    assert approve(client,pid).status_code==422
    db.session.refresh(member);assert member.tier.rank==0


def test_failed_refund_keeps_review_and_blocks_new_charge(client,member,pg,monkeypatch):
    fake,calls=pg;fake.amount=1
    pid=ready(client).json['data']['purchase']['id']
    def cancel(*args):raise kakaopay.KakaoPayError('unconfirmed')
    monkeypatch.setattr(kakaopay,'cancel',cancel)
    assert approve(client,pid).status_code==422
    assert db.session.get(SecurityAuditLog,pid).result=='REFUND_REQUIRED'
    assert ready(client).status_code==409


def test_ready_timeout_is_persisted_not_automatically_retried(client,member,pg,monkeypatch):
    def fail(*args,**kwargs):raise kakaopay.KakaoPayError('timeout')
    monkeypatch.setattr(kakaopay,'ready',fail)
    assert ready(client).status_code==502
    assert SecurityAuditLog.query.filter_by(action='membership.purchase').one().result=='REVIEW'
    assert ready(client).status_code==409
