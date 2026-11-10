# 03 · 개인 작업 내역

근거 링크는 모두 **팀 원본 저장소**의 커밋·PR입니다(개인 저장소는 민감정보 제거로 커밋 해시가 바뀌었기 때문).
계정 대응: `reereez15`=김준식(본인) · `gyeonggu`, `gyeonggumun`=문경구 · `kjo35861`, `KimJun-O`=김준오 · `ejdehdtjr-afk`=정동석

## 1. 팀 공통 vs 본인

| 구분 | 내용 | 근거 |
|---|---|---|
| 팀 공통 | 주제 선정(가상 통신사 L∞P), 4인 역할 분담, 브랜치 규칙(`main`/`develop`/기능 브랜치), 공통 계약(이벤트 형식·인시던트 API·환경변수) | `CONTRIBUTING.md`, `docs/contracts/` |
| 팀 공통 | 웹 2노드 배포·장애 시험(HTTP 200 224건), MySQL 복제·백업·복원(26개 테이블) — **문경구** | 팀 README, `docs/operations/` |
| 팀 공통 | pfSense·HAProxy·VPN·Suricata — **정동석** / Wazuh·Graylog·Zabbix·n8n 구성 — **김준오** | `network/`, `security/`, `monitoring/` |
| **본인 작성·검증** | React 고객·관리자 화면, Flask 인증·업무·보안 API, 데이터 모델, 백엔드 테스트 113개 | 아래 커밋 표 |
| **본인 작성·검증** | n8n이 부르는 내부 API(차단·잠금·회수·인시던트 등록)와 토큰 검증 — 김준오 님 워크플로가 호출하는 쪽 | `d2f7ec1`, `abf9332` |
| **본인 (이번 포트폴리오, 11-10)** | 민감정보 제거(저장소 기록·pfSense 백업), 혼자 설치용 compose·Wazuh 덧씌우기, 시나리오 재현 스크립트 3개, 앱 로그용 Graylog 규칙 ED-A1, n8n 워크플로 수정(식 오류·잠금 노드), 로컬 nginx 로그인 오류 수정 | 아래 6절, 이 저장소 `scripts/`, `docs/portfolio/` |
| 팀원 작업을 쓴 곳 | Graylog 콘텐츠 팩·n8n 워크플로·Wazuh 규칙·모의 공격 스크립트(**김준오**), pfSense 설정(**정동석**), k3s·MySQL·HAProxy 운영 문서(**문경구**) — 원본 구조는 그대로 두고 로컬 주소·비밀값 자리·오류만 고쳤다 | `monitoring/`, `security/pfsense/`, `docs/operations/` |
| 팀원 코드(웹 영역) | 멤버십 결제·대시보드 항목, 카카오페이 결제 복구, 포털 디자인 개편 — **문경구** | 아래 '팀원 작업' 표 |

## 2. 수치 (2026-11-10 측정)

| 항목 | 값 |
|---|---|
| 본인 커밋 (머지 제외) | 24개, 2026-10-19 ~ 11-03 |
| `web` 브랜치 PR (병합) | 11개 |
| 최초 작성 파일 | `backend/app` 65개 중 52개, `frontend/src` 75개 중 54개 |
| 백엔드 테스트 | 본인 작성 117개 통과 (팀 기간 113 + 11-10 보안 헤더 4) / 전체 154개 통과 |
| 프론트 빌드 | 성공 (모듈 90개) |

## 3. 날짜별 커밋
| 날짜 | 커밋 | 내용 | 파일 | +/- |
|---|---|---|---|---|
| 2026-10-19 | [`4df714c`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/4df714cf18e1f3d178a6279aba1bc2c9fec05e3a) | feat(web) : L∞P 웹·DB 1~9단계 초안 구현 | 101 | +7572 / -0 |
| 2026-10-19 | [`7f9e562`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/7f9e562b324c3e5be15624bc8146fa2922ececef) | feat(admin) : 관리자 역할 통합·회원 목록·요금제 변경·관제 바로가기 추가 | 30 | +1016 / -137 |
| 2026-10-20 | [`d2f7ec1`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/d2f7ec14abf1ac9e4f059f95ec44fa63e1ac632e) | feat(security) : 차단 IP·화이트리스트·계정 잠금·권한 점검·자동화 현황 추가 | 114 | +9745 / -0 |
| 2026-10-20 | [`e0a5d42`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/e0a5d423aafebc61f4fb02eb73ee5549b3def37e) | md 파일 추가 | 1 | +558 / -0 |
| 2026-10-20 | [`c1aa9c3`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/c1aa9c314a547b6b030e2738d6f159ba84ae9a61) | fix(security) : 잘못 들어간 telecom-update 폴더 제거 및 보안 대시보드 코드 반영 | 135 | +322 / -8516 |
| 2026-10-20 | [`c922a4d`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/c922a4d256ab64554111c9111236d10e1477adcf) | backend 실행 app.py변경 | 11 | +350 / -20 |
| 2026-10-20 | [`abf9332`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/abf93329139c209b81673ff0aaec7fbcbd2f7b59) | feat(security) : 자동화 기록 보기·삭제 추가 | 8 | +234 / -3 |
| 2026-10-20 | [`ab2d518`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/ab2d51880cf40d2b7b84bba91aef5c2cbaeaa781) | feat(security) : 보안 인시던트 삭제 추가 | 5 | +155 / -21 |
| 2026-10-20 | [`ed6baa8`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/ed6baa85f244e9806acb80a97d0df09d040b04b3) | feat(security) : Grafana 관제 지표 화면 추가 | 6 | +82 / -2 |
| 2026-10-21 | [`b593440`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/b593440e308d0a32f47b98067e557804c150373b) | 도커 파일 추가 | 1 | +24 / -0 |
| 2026-10-21 | [`b9166f3`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/b9166f3cbe9a0dbef8aa925f957dcf0f0caff0cc) | docker compose파일 추가 | 1 | +12 / -0 |
| 2026-10-21 | [`f812d4b`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/f812d4b342aeb1fd0a9b6e1e2471683b0541025b) | docker compose삭제및 frontend변경 | 6 | +159 / -57 |
| 2026-10-22 | [`bab7322`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/bab7322719f6c4d0723ac966a8f623d5105c15ed) | frontend 추가 | 5 | +105 / -768 |
| 2026-10-22 | [`89e7217`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/89e72175663058de5bf93edf21faf910d045144d) | feat(web) : 포인트 상점·등급별 적립·공지사항·카카오페이 테스트 결제, 상단 메뉴 정리 | 37 | +2956 / -122 |
| 2026-10-23 | [`2a60aae`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/2a60aae694a0c2275bf7b9956dd722d2016e9b48) | fix(frontend) : 넓은 화면에서 본문·상단 메뉴가 왼쪽으로 치우치던 레이아웃 가운데 정렬 | 1 | +6 / -3 |
| 2026-10-25 | [`7cf00a4`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/7cf00a426106319e0c5c9defd002a01bf09544de) | feat(frontend) : 다크 모드(시스템·라이트·다크) 및 색 변수 정리 | 9 | +328 / -45 |
| 2026-10-25 | [`32d3231`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/32d3231c694d519fefbf8049a94431d1047a72fb) | feat(frontend) : 고객 홈 브랜드 볼드·심각도 배지·카드 스타일 정리 | 5 | +163 / -42 |
| 2026-10-26 | [`3b7ba8b`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/3b7ba8b33f209e0391af8856295ed936f21f2b4c) | docker가 env파일을 최신화한것을 받아오기 | 2 | +15 / -6 |
| 2026-11-02 | [`33514fb`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/33514fbc74683bc2d63673a7e30e898d48498d0b) | feat(frontend) : 화면 테마에서 시스템 옵션 제거, 라이트/다크만 유지 | 3 | +16 / -23 |
| 2026-11-02 | [`250b42c`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/250b42c93574538bc01d7a8ad850702b7473e8cf) | feat(membership) : 등급 직접 구매(카카오페이·모의 카드) 연동 | 16 | +684 / -36 |
| 2026-11-03 | [`602812c`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/602812c59a7646212f4c197f6e554269dd4ef479) | feat(auth) : 자동 로그아웃 1시간으로 연장·접속 시간 표시, 멤버십 등급 구매 가격 14,900/34,900원 | 16 | +90 / -26 |
| 2026-11-03 | [`74372f8`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/74372f8623459659d94f179c0783500a98e0f32c) | refactor(membership) : 등급 구매를 DB 테이블 없이 처리(tid 쿠키 보관) | 13 | +279 / -446 |
| 2026-11-03 | [`2132bde`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/2132bde4909c99b44b3171fbdd364bbf6c5ef46f) | feat(auth) : 자동 로그아웃 30분으로 단축, 접속 시간을 상단 바로 이동 | 9 | +32 / -20 |
| 2026-11-03 | [`5d62b7b`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/5d62b7b355024889b89d6e6993c37dfaaf278788) | revert(membership) : 등급 직접 구매 제거 — main의 멤버십 작업과 충돌 회피 | 12 | +36 / -531 |

## 4. PR (`web` → 통합 브랜치)

| 날짜 | PR |
|---|---|
| 2026-11-03 | [#62](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/62) |
| 2026-11-02 | [#52](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/52) |
| 2026-10-26 | [#35](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/35) |
| 2026-10-26 | [#32](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/32) |
| 2026-10-23 | [#27](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/27) |
| 2026-10-22 | [#24](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/24) |
| 2026-10-21 | [#16](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/16) |
| 2026-10-21 | [#9](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/9) |
| 2026-10-20 | [#7](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/7) |
| 2026-10-20 | [#5](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/5) |
| 2026-10-19 | [#2](https://github.com/telecom-carrier-Loop/telecom-security-project/pull/2) |

## 5. 팀원 작업 중 웹 영역 (출처: 문경구, 본인 작업 아님)

| 날짜 | 커밋 | 내용 |
|---|---|---|
| 2026-11-03 | [`725990c`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/725990c) | 멤버십결제, 대시보드 항목추가 |
| 2026-11-02 | [`b3cecf5`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/b3cecf5) | 수정 자료 |
| 2026-11-02 | [`b1bbaa7`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/b1bbaa7) | feat: add PC1 resource monitoring and restore KakaoPay checkout |
| 2026-11-02 | [`650cc98`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/650cc98) | 최신화 |
| 2026-10-30 | [`1a5e493`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/1a5e493) | feat: add Kubernetes VM availability monitoring and daily work log |
| 2026-10-30 | [`f94b36c`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/f94b36c) | Revert "docker가 env파일을 최신화한것을 받아오기" |
| 2026-10-29 | [`83ae9f7`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/83ae9f7) | feat: improve membership management and admin security navigation |
| 2026-10-28 | [`9366f95`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/9366f95) | feat(ui): redesign Loop portal with T world inspired layout |
| 2026-10-27 | [`a0296d3`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/a0296d3) | zabbix연동/n8n요첟경로확인/웹디자인 수정 |
| 2026-10-22 | [`e0ea000`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/e0ea000) | fix(frontend) : 관리자 레이아웃의 미사용 import 제거 |
| 2026-10-22 | [`978d5d3`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/978d5d3) | https 부분을 위한 인증서 확인 |
| 2026-10-22 | [`aa0f74b`](https://github.com/telecom-carrier-Loop/telecom-security-project/commit/aa0f74b) | 의존성 파일 추가 |

## 6. 포트폴리오 정리 작업 (2026-11-10, 이 저장소)

근거는 이 저장소의 커밋([commits](https://github.com/reereez15/loop-telecom-portfolio/commits/main))과 아래 파일이다.

| 한 일 | 파일 | 검증 |
|---|---|---|
| 팀 저장소 기록에서 웹훅 1·토큰 3 제거 후 가져오기, 브랜치 정리(main 만) | `scripts/sanitize_repo.py`, `scripts/check_secrets.py` | `check_secrets.py --history` → 비밀값 없음 |
| pfSense 백업 비밀값 21개 제거, 구성 설명 | `scripts/sanitize_pfsense.py`, `security/pfsense/` | 제거 후 잔여 검사 0건 |
| 로컬 관제 스택 정의, n8n 2.40 고정 | `monitoring/compose/monitoring.compose.yaml`, `.env.example` | Graylog·n8n 기동 |
| n8n 본문 식 `}}` 오류 수정, 인시던트 노드 10개 켬 (팀 원본은 그대로, 수정본 따로) | `monitoring/n8n/workflows/portfolio/` | EX-05 → 인시던트 등록 54.2초 |
| 앱 로그용 브루트포스 규칙 ED-A1 + n8n 잠금 노드 수정 | `scripts/graylog_add_account_bruteforce.py`, 같은 워크플로 | S-A1 전 구간 7/7, 39.8초 |
| 로그인 제한 값 환경변수화, 시나리오 대기 옵션 | `backend/app/config.py`, `scripts/scenario_bruteforce.py` | HTTP 8/8, 테스트 150개 |
| 테스트가 개인 `.env` 를 읽지 않게 | `backend/app/config.py`, `backend/tests/conftest.py` | 이전 실패 1건 해결, 150 passed |
| 로컬 nginx Host 헤더 수정(브라우저 로그인 403) (팀 `nginx.conf` 는 그대로) | `nginx.portfolio.conf`, `nginx-admin.conf`, `compose.portfolio.yaml` | 브라우저 로그인 200 |
| 전 구간·EX-05 재현 스크립트, 캡처 7장 | `scripts/scenario_bruteforce_e2e.py`, `scripts/scenario_ex05_sqli.py`, `docs/portfolio/evidence/` | [02 시나리오](02_SCENARIOS.md) |
| Wazuh 로컬 실행용 덧씌우기(포트 127.0.0.1) | `monitoring/wazuh/compose.localhost.yaml` | ⬜ 실행 결과 미기록 |
| 보안 응답 헤더 추가(수업 노트 대조) | `backend/app/core/security_headers.py`, `nginx.portfolio.conf`, `nginx-admin.conf` (학원망 템플릿은 제안만) | 테스트 4개 추가, 154 passed |
| Wazuh → Graylog 파싱 규칙·연동 순서 | `monitoring/graylog/pipelines/wazuh_alert_parse.rule`, 설치 가이드 3-1 | ⬜ 미검증 |

## 7. 회의록·캡처

- 팀 저장소 `docs/meeting-notes/`는 비어 있습니다. 날짜별 진행은 `monitoring/진행 상황/`(김준오·문경구 작성)과 `docs/operations/`에 있습니다.
- 2026-11-10 로컬 재현 캡처 7장: [`evidence/screenshots/`](evidence/screenshots/) (설명은 [02 시나리오](02_SCENARIOS.md)). 실행 결과 원문: `evidence/*.txt`, `*.json`.
- 본인 회의 메모·학원 장비 캡처는 `docs/portfolio/evidence/`에 날짜를 붙여 추가합니다 (예: `2026-10-20_보안화면.png`).
- 캡처 전 확인: 주소창·터미널·`.env` 화면에 토큰·웹훅·비밀번호가 보이지 않을 것.

