"""고객 멤버십은 세 등급만 사용한다. ADMIN은 users.role의 관리 권한이다.

과거 rank 3 멤버십은 DB 행을 삭제하지 않고 VIP 정책으로 호환한다.
"""
TIER_NAMES = ("일반유저", "Plus", "VIP")
TIER_CODES = ("GENERAL", "PLUS", "VIP")

# 등급 직접 구매(업그레이드) 1회성 가격. rank 순서(0=일반유저, 1=Plus, 2=VIP).
# DB 컬럼을 쓰지 않고 코드 상수로 둔다 — 요금제 월 요금 기준 자동 가입 조건(MembershipTier.min_monthly_fee)과
# 별개 값이어야 하는데, 공용 DB 스키마를 바꾸지 않기 위한 선택이다. 가격 변경은 이 줄만 고치면 된다.
UPGRADE_PRICES = (0, 14900, 34900)


def upgrade_price(tier) -> int:
    return UPGRADE_PRICES[customer_rank(tier.rank)]


def customer_rank(rank):
    return min(rank, 2)


def customer_tier(tier):
    if tier.rank > 2:
        from ..models import MembershipTier
        return MembershipTier.query.filter_by(rank=2).first() or tier
    return tier


def tier_name(tier):
    return TIER_NAMES[customer_rank(tier.rank)] if tier.rank >= 0 else TIER_NAMES[0]


def tier_dict(tier):
    tier = customer_tier(tier)
    rank = customer_rank(tier.rank)
    return {"code": TIER_CODES[rank], "name": tier_name(tier), "rank": rank,
            "earn_rate_bp": tier.earn_rate_bp, "min_monthly_fee": tier.min_monthly_fee,
            "price": UPGRADE_PRICES[rank]}  # 등급 직접 구매(업그레이드) 1회성 가격
