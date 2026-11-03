"""멤버십 등급 직접 구매(업그레이드) — 모의 카드·카카오페이. 구매 이력 테이블 없이 동작한다."""
import json
from app.extensions import db
from app.models import MembershipAccount, User
from tests.conftest import csrf, login
from tests.test_shop_notices_kakaopay import kakao  # noqa: F401 (가짜 카카오페이 fixture 재사용)

PLUS, VIP = 14900, 34900


def _alice():
    return User.query.filter_by(email="alice@test.local").one()


def _rank():
    return MembershipAccount.query.filter_by(user_id=_alice().id).one().tier.rank


def test_tier_list_exposes_upgrade_price(client):
    login(client, "alice@test.local")
    tiers = {t["rank"]: t for t in client.get("/api/membership/me").json["data"]["membership"]["tiers"]}
    assert tiers[1]["price"] == PLUS and tiers[2]["price"] == VIP
    # 자동 가입 조건(min_monthly_fee)과는 다른 값이어야 한다
    assert tiers[1]["min_monthly_fee"] == 35000 and tiers[2]["min_monthly_fee"] == 60000


def test_mock_card_purchase_upgrades_tier(client):
    login(client, "alice@test.local")  # Plus(rank 1)
    res = client.post("/api/membership/upgrade",
                      json={"tier_rank": 2, "card_number": "4242424242424242"}, headers=csrf(client))
    assert res.status_code == 201
    data = res.json["data"]
    assert data["approved"] is True and data["upgrade"]["amount"] == VIP and data["upgrade"]["to_tier_rank"] == 2
    assert _rank() == 2


def test_mock_card_decline_keeps_tier(client):
    login(client, "alice@test.local")
    res = client.post("/api/membership/upgrade",
                      json={"tier_rank": 2, "card_number": "4000000000000002"}, headers=csrf(client))
    assert res.status_code == 200 and res.json["data"]["approved"] is False
    assert _rank() == 1


def test_cannot_buy_same_or_lower_tier(client):
    login(client, "alice@test.local")  # rank 1
    res = client.post("/api/membership/upgrade",
                      json={"tier_rank": 1, "card_number": "4242424242424242"}, headers=csrf(client))
    assert res.json["error"]["code"] == "ALREADY_AT_OR_ABOVE"
    assert _rank() == 1


def test_requires_membership(client, app):
    login(client, "alice@test.local")
    with app.app_context():
        MembershipAccount.query.filter_by(user_id=_alice().id).delete()
        db.session.commit()
    res = client.post("/api/membership/upgrade",
                      json={"tier_rank": 2, "card_number": "4242424242424242"}, headers=csrf(client))
    assert res.json["error"]["code"] == "NOT_MEMBER"


def test_kakaopay_ready_then_approve_upgrades_tier(client, kakao):
    fake, calls = kakao
    login(client, "alice@test.local")
    ready = client.post("/api/membership/upgrade/kakaopay/ready", json={"tier_rank": 2}, headers=csrf(client))
    assert ready.status_code == 201
    assert ready.json["data"]["redirect_url"].startswith("https://online-pay.kakao.com/")
    sent = calls[0][1]
    assert sent["total_amount"] == VIP
    assert sent["partner_order_id"] == f"upg-{_alice().id}-2"     # 승인 때 서버가 다시 만들어 대조하는 주문번호
    assert sent["approval_url"] == "http://localhost:5173/membership/kakaopay/approve?rank=2"

    ok = client.post("/api/membership/upgrade/kakaopay/approve", json={"pg_token": "abc123"}, headers=csrf(client))
    assert ok.status_code == 200 and ok.json["data"]["upgrade"]["amount"] == VIP
    assert _rank() == 2


def test_kakaopay_approve_without_ready_is_rejected(client, kakao):
    login(client, "alice@test.local")
    res = client.post("/api/membership/upgrade/kakaopay/approve", json={"pg_token": "abc123"}, headers=csrf(client))
    assert res.json["error"]["code"] == "NO_PENDING_PAYMENT"
    assert _rank() == 1


def test_kakaopay_amount_mismatch_cancels_and_keeps_tier(client, kakao):
    fake, calls = kakao
    fake.approve_amount = 1  # 승인 금액을 일부러 다르게
    login(client, "alice@test.local")
    client.post("/api/membership/upgrade/kakaopay/ready", json={"tier_rank": 2}, headers=csrf(client))
    bad = client.post("/api/membership/upgrade/kakaopay/approve", json={"pg_token": "abc"}, headers=csrf(client))
    assert bad.json["error"]["code"] == "AMOUNT_MISMATCH"
    assert any(path.endswith("/cancel") for path, _ in calls)
    assert _rank() == 1


def test_kakaopay_abort_clears_pending(client, kakao):
    login(client, "alice@test.local")
    client.post("/api/membership/upgrade/kakaopay/ready", json={"tier_rank": 2}, headers=csrf(client))
    assert client.post("/api/membership/upgrade/kakaopay/abort", json={"reason": "cancel"},
                       headers=csrf(client)).status_code == 200
    # 취소 뒤에는 이어서 승인할 수 없다
    again = client.post("/api/membership/upgrade/kakaopay/approve", json={"pg_token": "abc"}, headers=csrf(client))
    assert again.json["error"]["code"] == "NO_PENDING_PAYMENT"
    assert _rank() == 1


def test_kakaopay_tampered_cookie_rank_is_rejected(client, kakao):
    """싼 등급으로 결제해 놓고 쿠키의 rank 를 비싼 등급으로 바꿔도 승인되지 않는다.

    서버가 주문번호를 "세션의 user_id + 쿠키의 rank" 로 다시 만들어 보내므로,
    카카오페이가 보관한 주문번호(결제 당시의 등급)와 달라 거절된다.
    """
    login(client, "alice@test.local")  # rank 1 → Plus 는 못 사므로 VIP(2) 로 준비한 뒤 rank 를 거꾸로 위조
    client.post("/api/membership/upgrade/kakaopay/ready", json={"tier_rank": 2}, headers=csrf(client))
    from tests.conftest import HOST
    pending = client.get_cookie("telecom_upgrade_pending", domain=HOST)
    tampered = json.dumps({"tid": json.loads(pending.decoded_value)["tid"], "rank": 1})
    client.set_cookie("telecom_upgrade_pending", tampered, domain=HOST)

    res = client.post("/api/membership/upgrade/kakaopay/approve", json={"pg_token": "abc"}, headers=csrf(client))
    assert res.json["error"]["code"] == "PG_ERROR"
    assert _rank() == 1
