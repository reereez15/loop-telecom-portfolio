# 공개 관리자 차단과 재배포 정책 일치

2026-11-04, Asia/Seoul. 공개 고객 입구 `https://192.168.3.30`에서 ADMIN 로그인 계정으로도 관리자 기능이 노출되던 문제에 대해 공개 관리자 UI/API를 404로 막고 관리 전용 `.7.178:9443/admin`을 유지하는 정책으로 변경했다. 2026-11-02의 공개 관리자 차단 제거 절차를 대체한다.

## 현장 적용과 직접 확인 범위

사용자가 제공한 PC1 Ubuntu `pc1-k3s` 출력에서 API 두 Pod 각각 관리자 경로 46개·미인증 401 검사, 후보 `nginx -t`, 공개 Edge 두 Pod 순차 교체, 실제 차단 규칙과 Ready 2개를 확인했다. 적용 도구는 별도 전달한 `loop-public-admin-guard.py`였다. 저장소의 새 도구로 운영 서버를 재적용한 결과는 아니다.

현재 Windows PC에서 새 HTTP 요청으로 재확인했다.

| 검사 | 결과 |
|---|---|
| 공개 `/` | 200 |
| 공개 `/api/health/ready` | 200, `status=ok`, `database=ok` |
| 공개 `/admin`, `/admin/`, `/admin/customers` | 404 |
| 공개 `/api/admin`, `/api/admin/`, `/api/admin/dashboard`, `/api/admin/monitoring-links` | 404 |
| 공개 `/api/internal`, `/api/internal/` 및 실제 내부 API 경로 | 404 |
| 공개 인코딩·정규화 경로 `/api/%61dmin/dashboard`, `//api/admin/dashboard`, `/api/x/../admin/dashboard`, `/%61dmin` | 404 |
| 관리 전용 `/admin` | 직접 HTTP 200 확인, 사용자 보고로 ADMIN 로그인·조회·새로고침 정상 |

요청에는 인증 쿠키·토큰을 전송하지 않았다. 자체 인증서 환경의 HTTP 응답 확인을 위해 curl `--insecure`를 사용했으므로 인증서 신뢰·호스트명 검증 결과는 아니다. 무인증 404 요청과 설정 검사만으로 모든 로그인 상태의 실제 업무 검증을 대체하지 않는다.

## 저장소 변경

- `k3s-admin-access.py`는 공개 차단 제거 대신 네 규칙을 추가·유지한다. 부분/알 수 없는 정책은 덮어쓰지 않으며 구버전의 차단 해제 계획을 거부한다.
- 기존 TLS·Web/API upstream·내부 API 차단을 보존하고 공개 ConfigMap 한 키만 조건부 변경한다. 두 Pod가 모두 이미 보호되면 재시작하지 않는다.
- 릴리스는 배포 전후 공개 ConfigMap과 양쪽 `nginx -T`의 차단·내부 경계·고객 upstream, 관리 Edge Ready, 두 API의 ADMIN 보호를 확인한다. 정책 불일치 시 배포를 멈추며 Edge를 덮어쓰지 않는다.
- 이미지와 검증 스크립트를 같은 clean 소스 커밋에서 패키징해 두 VM에 전달한다. 사설 Edge, pfSense, Service/NodePort, DB, Secret은 이 정책 변경의 수정 대상이 아니다.
- 기존 호스트 Nginx/로컬 Compose 공개 예제에는 이미 네 차단이 있으며 회귀 테스트에서 유지 여부를 확인한다.

## 사용자가 추가로 완료한 시험

- [x] 허용 PC에서 관리 전용 ADMIN 로그인·데이터 조회·새로고침 정상 — 사용자 보고.
- [x] 비허용·VPN 미연결 PC의 관리 전용 접속 차단 시험 완료 — 사용자 보고.

개별 PC의 출발지 주소·화면 증빙을 이 문서에 첨부한 것은 아니며, 위 두 항목은 사용자의 현장 완료 보고와 직접 수행한 HTTP 검사를 구분해 기록했다.

## 로컬 검증

- k3s 정책·자동화 회귀 테스트 38개와 릴리스 회귀 테스트 14개, 총 52개 통과.
- 격리된 실제 Nginx fixture에서 기존 TLS/프록시 경계와 새 도구가 생성한 후보를 검사했다. `nginx -t/-T`, 고객 200, 관리자·내부 API·정규화 경로 404 통과.
- Python 및 PowerShell 문법 검사와 `git diff --check` 통과.

## 별도 후속 현장 시험

- [ ] 실제 VPN 클라이언트의 경로·관리 인증.
- [ ] HAProxy 두 서버 UP과 고객 업무·관제·자동화 회귀.
- [ ] 실제 서비스 목록을 기준으로 직접 NodePort·다른 주소/포트 우회 제한.
- [ ] 이 PR 병합 후 새 릴리스 도구로 양 노드 이미지 재배포 및 현장 복구 시험.

공개 관리자 차단 및 위 두 가지 현장 시험 완료와 모든 우회 경로의 제한 완료를 구분한다. pfSense 원본 출발지 규칙의 상세 검토와 NodePort 경계·VPN은 네트워크 담당자와 추가 검증해야 한다. 현재 PC에서 관리 로그인 화면이 200이라는 사실만으로 비허용 PC 차단을 판단하지 않는다.

운영 명령과 검증 절차: [공개 관리자 차단](../runbooks/academy-admin-access.md), [클린 릴리스](../runbooks/webapi-clean-release.md).
