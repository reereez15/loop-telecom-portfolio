# 02 · 시나리오 재현 (공격 → 로그 수집 → 탐지 → n8n 자동 대응 → 복구)

## S-A1 · 로그인 무차별 대입 → 계정 자동 잠금 (본인 담당, 직접 재현)

| 단계 | 하는 일 | 관련 코드 |
|---|---|---|
| 공격 | 같은 계정에 틀린 비밀번호 6회 | `POST /api/auth/login` |
| 로그 수집 | 실패마다 `auth.login.failed`, 한도 초과 시 `auth.rate_limited` 이벤트 (이메일 대신 `account_hash`) | `auth/service.py`, `core/logging.py`, `core/gelf.py` |
| 탐지 | 같은 `account_hash` 실패 ≥ 5 (15분) | 앱: `LOGIN_MAX_PER_ACCOUNT` / Graylog: 아래 개선 규칙 |
| 자동 대응 | n8n `8- 브루트포스 계정잠금` → `POST /api/internal/account-locks` (전용 토큰) | `incidents/protection_routes.py` |
| 복구 | 관리자 콘솔에서 잠금 해제 → 15분 창이 지나면 정상 로그인 | `POST /api/admin/customers/{id}/unlock` |

**테스트 명령**
```powershell
# A) Docker 없이 (앱 내부 + SQLite)
cd backend; python ..\scripts\scenario_bruteforce.py --out ..\docs\portfolio\evidence\S-A1_inprocess.json
# B) 로컬 Compose 를 띄운 뒤 실제 HTTPS 로
python scripts/scenario_bruteforce.py --base-url https://localhost:8443 --admin-url https://localhost:8444 --ca .secrets/tls/ca.crt --out docs/portfolio/evidence/S-A1_http.json
```

**기대 결과와 실측 결과**

| # | 단계 | 기대 | 실측 A (2026-11-10, 5회) | 실측 B |
|---|---|---|---|---|
| 1 | 공격 6회 | 401×5 → 429 | `[401,401,401,401,401,429]` ✅ | ⬜ |
| 2 | 로그 | 실패 5건 + 제한 1건, 이메일 원문 0 | 5건 + 1건, 원문 0 ✅ | Graylog `event_type:auth.login.failed` ⬜ |
| 3 | 탐지 | 같은 해시 실패 ≥ 5 | 5건 일치 ✅ | Graylog Alert ⬜ |
| 4 | 자동 대응 | 201 locked=true | 201 CREATED ✅ | n8n Execution ⬜ |
| 4-1 | 잘못된 토큰 | 401 | 401 ✅ | ⬜ |
| 5-1 | 잠금 확인 | 올바른 비밀번호도 403 | 403 ACCOUNT_LOCKED ✅ | ⬜ |
| 5-2 | 관리자 해제 | 200 | 200 ✅ | ⬜ |
| 5-3 | 정상 로그인 | 200 | 200 ✅ | ⬜ |
| | 전체 | 8/8 | **8/8, 999~1,142 ms** | ⬜ |

증거: [evidence/S-A1_inprocess.txt](evidence/S-A1_inprocess.txt), [S-A1_inprocess.json](evidence/S-A1_inprocess.json)
캡처할 것(B 실행 후): ① 응답 코드 출력 ② Graylog 검색 결과 ③ n8n 실행 기록 ④ 관리자 콘솔 계정 잠금 목록 ⑤ 해제 후 로그인 화면

## 팀 시나리오 (학원 실습망, 담당: 김준오 · 관제/자동화)

모의 로그 스크립트: `monitoring/graylog/attack-test/PC2_to_PC1/` (학원 Graylog 주소 `192.168.3.18` → 로컬은 `127.0.0.1`로 바꿔 실행)

| 시나리오 | 탐지 규칙 | 자동 대응 | 팀 기록(출처) | 본인 재현 |
|---|---|---|---|---|
| EX-05 SQL Injection | ED-EX-05 `rule:sqli-detected` | n8n → 인시던트 등록 + Discord | `attack-test` 스크립트 | ⬜ 로컬 2단계에서 |
| EX-04 심야 로그인 성공 | ED-EX-04 | 인시던트 등록 | 〃 | ⬜ |
| ED-01 관리자 권한 오용 | `rule:priv-unauthorized-admin` | `/api/internal/role-revocations` 권한 회수 | 10-21 n8n 실행 #370 성공 (김준오 작업현황) | ⬜ |
| ED-05 다중 공격 상관 | 같은 IP 브루트포스+포트스캔 | 인시던트 + Discord | 10-21 n8n #371 성공 (〃) | — |
| ED-09 웹스캐너 404 폭주 | 404 35건 → `count()=35` | `/api/internal/ip-blocks` | 10-21 탐지·연동 확인 (〃) | — |
| WZ-100230~237 리눅스 호스트 | Wazuh 규칙 8종 | Graylog → n8n → 인시던트 | 11-04 발표: 파일 생성·수정·삭제 탐지 (팀 README) | 3단계 logtest ⬜ |

※ 실측 칸은 본인이 직접 돌린 것만 채웁니다. 팀 기록 칸은 출처의 내용을 옮긴 것입니다.
