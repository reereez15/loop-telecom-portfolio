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

## 업그레이드 카드 — 등급 직접 구매 (2026-11-03)

등급(Plus·VIP)을 1회성 결제로 바로 구매할 수 있다. 모의 카드와 카카오페이 테스트 결제 둘 다 지원하며,
**결제가 승인되어야만** 등급이 올라간다.

가격은 `membership/tiers.py`의 코드 상수 `UPGRADE_PRICES`(Plus 14,900원·VIP 34,900원)이며 `tier_dict()`의
`price` 필드로 내려간다. 요금제 월 요금 기준 자동 가입 조건(`MembershipTier.min_monthly_fee`, 35,000·60,000원)과는
별개 값이다 — 자동 가입 조건보다 구매 가격이 낮아, 하나로 합쳐 쓰면 요금제만으로 상위 등급이 열려버린다.

### 저장 테이블을 두지 않는다

구매 이력 테이블을 새로 만들지 않는다(공용 DB 스키마를 바꾸지 않기로 함). 그래서:

- **모의 카드**: 한 번의 요청 안에서 승인→등급 반영까지 끝나므로 보관할 상태가 없다.
- **카카오페이**: ready 응답의 `tid`를 HttpOnly 쿠키(`telecom_upgrade_pending`, 30분)에 담아 approve 때 되돌려 받는다.
  카카오페이는 복귀 시 `pg_token`만 붙여주고, `approval_url`은 ready 호출 시점에 미리 넘기는 값이라 tid를 URL에 실을 수 없다.
- 한계: 구매 이력·관리자 조회 화면이 없고(결제 기록은 카카오페이 쪽에만 남는다), 쿠키가 지워지면 승인을 이어갈 수 없다
  (승인 전이라 돈은 빠지지 않는다).

### 조작 방지

- 금액은 항상 서버가 다시 계산한다. 요청 본문의 금액은 받지 않는다.
- 주문번호를 `upg-{user_id}-{rank}`로 정해두고, approve 때 **세션의 user_id와 쿠키의 rank로 서버가 다시 만들어** 보낸다.
  쿠키를 고쳐 더 비싼 등급을 받으려 하면 카카오페이가 보관한 주문번호와 달라 승인이 거절된다.
- 승인 응답의 `amount.total`이 서버 계산 가격과 다르면 즉시 카카오페이 결제를 취소한다.
- 등급 반영은 "구매 시작 시점 등급과 지금 등급이 같을 때만" 조건부 UPDATE 한다. 그사이 바뀌었으면 반영하지 않고
  카카오페이 결제도 취소한다.

### 엔드포인트

- `POST /api/membership/upgrade` — 모의 카드. 본문 `{ "tier_rank": 1|2, "card_number": "..." }`.
  승인되면 201 + `{approved: true, upgrade: {...}}`, 카드가 거절되면 200 + `{approved: false, upgrade: null}`.
- `POST /api/membership/upgrade/kakaopay/ready` — 본문 `{ "tier_rank": 1|2 }` → `{redirect_url, amount}` + 대기 쿠키
- `POST /api/membership/upgrade/kakaopay/approve` — 본문 `{ "pg_token": "..." }` (tid·rank는 쿠키에서 읽는다)
- `POST /api/membership/upgrade/kakaopay/abort` — 결제창에서 취소/실패하고 돌아온 경우. 대기 쿠키만 지운다.
- 현재 등급 이하로는 구매할 수 없다(`ALREADY_AT_OR_ABOVE`). 미가입 고객은 `NOT_MEMBER`(먼저 `/api/membership/join`).
- ready 없이 approve를 부르면 `NO_PENDING_PAYMENT`.
