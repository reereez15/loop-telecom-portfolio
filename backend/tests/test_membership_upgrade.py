"""멤버십 등급 직접 구매(업그레이드) — 모의 카드·카카오페이."""
import pytest

from app.extensions import db
from app.models import MembershipAccount, MembershipTier, MembershipUpgrade, User
from app.payments import kakaopay
from tests.conftest import csrf, login
from tests.test_shop_notices_kakaopay import idem, kakao  # noqa: F401 (fixture 재사용)


def _alice():
    return User.query.filter_by(email="alice@test.local").one()


def test_mock_card_purchase_upgrades_tier(client):
    login(client, "alice@test.local")
    res = client.post("/api/membership/upgrade", json={"tier_rank": 2, "card_number": "4242424242424242"},
                      headers=idem(client))
    assert res.status_code == 201
    body = res.json["data"]["upgrade"]
    assert body["status"] == "SUCCEEDED" and body["amount"] == 34900 and body["to_tier_rank"] == 2
    acc = MembershipAccount.query.filter_by(user_id=_alice().id).one()
    assert acc.tier.rank == 2  # VIP(GOLD 행)로 반영됨


def test_mock_card_decline_does_not_change_tier(client):
    login(client, "alice@test.local")
    res = client.post("/api/membership/upgrade", json={"tier_rank": 2, "card_number": "4000000000000002"},
                      headers=idem(client))
    assert res.status_code == 201 and res.json["data"]["upgrade"]["status"] == "FAILED"
    acc = MembershipAccount.query.filter_by(user_id=_alice().id).one()
    assert acc.tier.rank == 1  # 그대로 Silver


def test_cannot_purchase_same_or_lower_tier(client):
    login(client, "alice@test.local")  # rank 1
    res = client.post("/api/membership/upgrade", json={"tier_rank": 1, "card_number": "4242424242424242"},
                      headers=idem(client))
    assert res.json["error"]["code"] == "ALREADY_AT_OR_ABOVE"


def test_requires_membership(client, app):
    login(client, "alice@test.local")
    with app.app_context():
        MembershipAccount.query.filter_by(user_id=_alice().id).delete()
        db.session.commit()
    res = client.post("/api/membership/upgrade", json={"tier_rank": 2, "card_number": "4242424242424242"},
                      headers=idem(client))
    assert res.json["error"]["code"] == "NOT_MEMBER"


def test_mock_idempotent_replay(client):
    login(client, "alice@test.local")
    h = idem(client)
    first = client.post("/api/membership/upgrade", json={"tier_rank": 2, "card_number": "4242424242424242"}, headers=h)
    again = client.post("/api/membership/upgrade", json={"tier_rank": 2, "card_number": "4242424242424242"}, headers=h)
    assert again.json["data"]["replayed"] is True
    assert again.json["data"]["upgrade"]["id"] == first.json["data"]["upgrade"]["id"]
    assert MembershipUpgrade.query.count() == 1


def test_kakaopay_ready_and_approve_upgrades_tier(client, kakao):
    fake, calls = kakao
    login(client, "alice@test.local")
    res = client.post("/api/membership/upgrade/kakaopay/ready", json={"tier_rank": 2}, headers=idem(client))
    assert res.status_code == 201
    redirect = res.json["data"]["redirect_url"]
    assert redirect.startswith("https://online-pay.kakao.com/")
    ready_payload = calls[0][1]
    assert ready_payload["total_amount"] == 34900
    assert ready_payload["approval_url"].startswith("http://localhost:5173/membership/kakaopay/approve?payment_id=")

    uid = res.json["data"]["upgrade"]["id"]
    ok = client.post("/api/membership/upgrade/kakaopay/approve", json={"upgrade_id": uid, "pg_token": "abc123"},
                     headers=csrf(client))
    assert ok.status_code == 200 and ok.json["data"]["upgrade"]["status"] == "SUCCEEDED"
    acc = MembershipAccount.query.filter_by(user_id=_alice().id).one()
    assert acc.tier.rank == 2


def test_kakaopay_amount_mismatch_cancels_and_keeps_tier(client, kakao):
    fake, calls = kakao
    fake.approve_amount = 1  # 승인 금액을 일부러 다르게
    login(client, "alice@test.local")
    res = client.post("/api/membership/upgrade/kakaopay/ready", json={"tier_rank": 2}, headers=idem(client))
    uid = res.json["data"]["upgrade"]["id"]
    bad = client.post("/api/membership/upgrade/kakaopay/approve", json={"upgrade_id": uid, "pg_token": "abc"},
                      headers=csrf(client))
    assert bad.json["error"]["code"] == "AMOUNT_MISMATCH"
    assert any(p.endswith("/cancel") for p, _ in calls)
    acc = MembershipAccount.query.filter_by(user_id=_alice().id).one()
    assert acc.tier.rank == 1


def test_kakaopay_abort(client, kakao):
    login(client, "alice@test.local")
    res = client.post("/api/membership/upgrade/kakaopay/ready", json={"tier_rank": 2}, headers=idem(client))
    uid = res.json["data"]["upgrade"]["id"]
    aborted = client.post("/api/membership/upgrade/kakaopay/abort", json={"upgrade_id": uid, "reason": "cancel"},
                          headers=csrf(client))
    assert aborted.json["data"]["upgrade"]["status"] == "CANCELED"


def test_admin_can_list_upgrades(client):
    login(client, "alice@test.local")
    client.post("/api/membership/upgrade", json={"tier_rank": 2, "card_number": "4242424242424242"}, headers=idem(client))
    assert client.get("/api/admin/membership/upgrades").status_code == 403
    client.post("/api/auth/logout", headers=csrf(client))
    login(client, "admin@test.local")
    rows = client.get("/api/admin/membership/upgrades").json["data"]["upgrades"]
    assert rows and rows[0]["customer_name"] == _alice().name
