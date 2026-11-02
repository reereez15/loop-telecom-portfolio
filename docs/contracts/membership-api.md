# 멤버십 — A / 인프라 담당 / C

예정 경로: GET /api/membership/me, /transactions, /benefits; POST /api/membership/benefits/{id}/redeem.

서버가 비용·등급·자격을 판단하고 차감과 이력을 한 트랜잭션에 저장합니다. Idempotency-Key와 본문 해시·고유 제약을 사용합니다. 같은 키/같은 내용은 기존 결과, 같은 키/다른 내용은 409입니다. 다른 키를 사용한 중복 혜택도 업무 정책·원장 제약으로 확인합니다. ADMIN 정책 관리는 허용하되 잔액 직접 덮어쓰기 API는 만들지 않습니다.

## 등급 및 관리자 변경 (2026-10-29)

| rank | 표시 등급 | 공개 code | 기존 DB code | 기존 적립률 |
|---|---|---|---|---|
| 0 | 일반유저 | GENERAL | BASIC | 0.5% |
| 1 | Plus | PLUS | SILVER | 1% |
| 2 | VIP | VIP | GOLD | 2% |

고객 멤버십은 일반유저·Plus·VIP 세 등급이다. ADMIN은 users.role의 관리자 역할이며 구매·지정 가능한 고객 멤버십이 아니다. 과거 rank 3 행·외래키·포인트 원장은 삭제하거나 일괄 변경하지 않고, 고객 조회·신규 적립·혜택·상점 조건에서는 VIP(rank 2) 정책으로 호환한다. 기존 잔액은 보존한다. 관리자 지정 후 요금제 변경으로 등급을 덮어쓰지 않는다.

- `GET /api/membership/tiers`: 로그인 후 고객용 세 등급 조회. Admin 등급은 반환하지 않는다.
- `GET /api/admin/membership/tiers`: 실제 ADMIN 세션만 고객용 세 등급 목록 조회 가능.
- `PATCH /api/admin/membership/customers/{user_id}/tier`: 실제 ADMIN 세션과 CSRF 검증. 본문 `{ "rank": 0~2 정수, "reason": "1~300자 변경 사유" }`. rank 3은 422로 거부한다.
- 대상은 활성 CUSTOMER 계정이다. 탈퇴 계정은 409, 없는 대상이나 실제 ADMIN 계정은 404다.
- 미가입 고객을 지정하면 포인트 0의 멤버십을 생성한다. 기존 회원의 잔액·원장은 변경하지 않는다. 가입 보너스를 추가 지급하지 않는다.
- 변경 전후 rank·사유·행위자·대상을 `security_audit_logs`의 `membership.tier.changed`로 변경과 같은 트랜잭션에 저장한다.
- 동시 변경 충돌은 409로 반환한다. 실제 사용자 role·세션 권한·허용목록은 변경하지 않는다.

## 업그레이드 카드 — 등급 직접 구매 (2026-11-02)

등급(Plus·VIP)을 1회성 결제로 바로 구매할 수 있다. 가격은 `membership/tiers.py`의 코드 상수 `UPGRADE_PRICES`
(Plus 14,900원·VIP 34,900원)이며 `tier_dict()`의 `price` 필드로 내려간다. 요금제 월 요금 기준 자동 가입 조건
(`MembershipTier.min_monthly_fee`, 35,000·60,000원)과는 별개 값이다 — 처음엔 하나로 합쳐 썼다가, 자동 가입 조건보다
구매 가격을 낮게 책정하면서(요금제만 쓰면 상위 등급이 공짜로 열려버리는 문제가 생겨) 분리했다. 공용 DB 스키마를 바꾸지
않으려고 가격 컬럼 대신 코드 상수로 두었고, 가격 변경은 그 한 줄만 고치면 된다.
모의 카드·카카오페이 둘 다 지원하며, payments 모듈과 같은 방어를 쓴다:
서버가 가격을 다시 계산(요청 금액은 참고만), `(user_id, idempotency_key)` 멱등, 카카오페이 승인 금액 불일치 시 즉시 취소.

새 테이블 `membership_upgrades` (Migration `a1f5c9e2b4d7`, 수동 적용은 `database/schema/05_membership_upgrades.sql`).
동시성: 계정 행을 잠그고 "구매 시작 시점 등급과 지금 등급이 같을 때만" 조건부 UPDATE로 반영한다 — 그사이 관리자가 등급을
바꿨거나 다른 채널로 이미 업그레이드했으면 거절하고, 카카오페이 결제는 취소한다. 등급을 환불로 되돌리는 정책이 아직
없어 관리자 환불 API는 없다(성공한 구매를 취소하려면 당분간 `PATCH /api/admin/membership/customers/{id}/tier`로 수동 변경).

- 가격·구매 가능 여부는 별도 엔드포인트 없이 기존 `GET /api/membership/me`·`/api/membership/tiers` 응답(tier_dict 의 `price`)로 내려간다.
- `POST /api/membership/upgrade`: 모의 카드. 본문 `{ "tier_rank": 1|2, "card_number": "..." }` + `Idempotency-Key`
- `POST /api/membership/upgrade/kakaopay/ready|approve|abort`: 카카오페이(payments/kakaopay.py 재사용, `section="membership"` →
  프런트 복귀 경로가 `/membership/kakaopay/...`)
- `GET /api/membership/upgrade/me`: 내 구매 내역 (최근 20건)
- `GET /api/admin/membership/upgrades`: 실제 ADMIN 세션만, 전체 구매 내역 조회(최근 100건)
- 현재 등급 이하로는 구매할 수 없다(`ALREADY_AT_OR_ABOVE`). 미가입 고객은 `NOT_MEMBER`(먼저 `/api/membership/join`).
