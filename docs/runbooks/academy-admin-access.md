# 공개 관리자 차단과 관리 전용 입구 유지

2026-11-04 정책: 공개 `https://192.168.3.30`은 고객용이다. ADMIN 계정이 로그인되어 있어도 공개 관리자 UI/API는 404여야 한다. 관리 작업은 `https://192.168.7.178:9443/admin`에서 ADMIN 인증 후 수행한다.

과거의 공개 관리자 404 제거 절차를 대체한다. 예전 브랜치나 Ubuntu 홈에 남은 **차단 해제용** `k3s-admin-access.py`를 실행하지 않는다. 현재 도구는 네 차단 규칙을 추가·유지하며 이전 `telecom-admin-access-v1` 작업 폴더를 거부한다.

## 경계와 담당 범위

| 입구 | 기대 동작 |
|---|---|
| 공개 `/`, 고객 API, `/api/health/ready` | 고객 기능 유지, readiness 200·DB 정상 |
| 공개 `/admin`, `/admin/*`, `/api/admin`, `/api/admin/*` | 모든 계정에 404 |
| 공개 `/api/internal`, `/api/internal/*` | 기존 404 유지 |
| 관리 전용 `.7.178:9443/admin` | 허용 PC·승인된 VPN에서 ADMIN 로그인·조회 |
| 비허용 PC의 관리 전용 새 연결 | pfSense에서 차단 |

PC1·2·3 Windows 주소는 `.3.18`, `.3.19`, `.3.20`이며 pfSense `ADMIN_PCS` 및 승인된 VPN의 원본 출발지 제한을 현장에서 검증해야 한다. SNAT 후 Nginx에 보이는 주소만으로 원래 PC를 구분했다고 판단하지 않는다. 이 도구는 pfSense, VPN, 방화벽, Service/NodePort, 사설 Edge, DB 또는 Secret을 변경하지 않는다. **공개 관리자 차단 성공은 전체 PC 접근 제한 완료를 뜻하지 않는다.**

## 사전 확인

1. 관리 전용 주소에서 ADMIN 로그인·실제 데이터 조회·새로고침을 확인한다.
2. 공개 고객 기능과 pfSense HAProxy의 `pc1-web`, `pc2-web` UP을 확인한다.
3. 다른 담당자의 Edge 변경·배포와 작업 시간을 겹치지 않는다.
4. PR이 main에 병합된 뒤 깨끗한 PC1 Ubuntu 저장소에서 최신 코드를 사용한다. Windows PowerShell에서 k3s를 실행하지 않는다.

PC1 Ubuntu:

```bash
cd ~/telecom-security-project
git status --short --branch
# 작업 트리와 브랜치가 맞는지 확인한 후에만 최신 main을 받는다.
git pull --ff-only
hostname
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl -n telecom get deployment telecom-edge telecom-admin-edge
```

## 백업·후보 검사

```bash
sudo -v
python3 infrastructure/tools/k3s-admin-access.py plan
```

두 API Pod에서 ADMIN 보호와 미인증 401을 감사하고, 공개 Edge 두 Pod Ready·관리 Edge Ready·ConfigMap 단독 사용을 검사한다. 기존 TLS·프록시 헤더·Web/API upstream·내부 API 차단을 보존하고 다음 네 규칙만 공개 HTTPS server에 추가한다.

```nginx
location = /admin { return 404; }
location ^~ /admin/ { return 404; }
location = /api/admin { return 404; }
location ^~ /api/admin/ { return 404; }
```

원본 ConfigMap·Deployment와 후보는 `~/.local/state/telecom-public-admin-guard/` 아래에 저장한다. 후보를 양쪽 공개 Edge에서 `nginx -t`로 검사한다. 계획 단계는 운영 ConfigMap 갱신·Pod 교체를 하지 않으며 검사 임시 파일만 만들었다가 정리한다.

`PLAN_OK`와 `WORK_DIR`를 기록한다. 부분 차단, 알 수 없는 관리자 location/include, 여러 server, server 수준의 rewrite/error_page 등 자동으로 안전성을 확인할 수 없는 구조는 수동 검토를 요구한다. 검사를 통과시키려고 차단 규칙을 지우지 않는다.

## 적용과 상태 확인

`WORK_DIR`의 실제 경로를 변수에 넣는다. `PLAN_OK`와 관리 전용 로그인·조회를 확인한 후:

```bash
loopGuardWork='/home/loop/.local/state/telecom-public-admin-guard/실제-WORK_DIR'
sudo -v
python3 infrastructure/tools/k3s-admin-access.py apply --work-dir "$loopGuardWork"
python3 infrastructure/tools/k3s-admin-access.py status --work-dir "$loopGuardWork"
```

UID/resourceVersion/원문 조건을 원자적으로 확인하며 `telecom-edge-config`의 `nginx.conf` 키만 변경한다. 공개 Pod를 하나씩 교체하고 두 Pod Ready 후 다음으로 진행한다. 이미 ConfigMap과 두 Pod 모두 차단되어 있으면 `ALREADY_PROTECTED`로 종료한다. ConfigMap만 새 정책이고 Pod는 구버전인 경우 순차 교체한다. 기존 연결이 모두 무손실이라고 보장하지 않는다.

적용 후 `applied-needs-http-tests`는 외부 HTTP·로그인 시험이 남았다는 뜻이다. 외부에서 시험한 결과가 이 상태 문자열에 자동 기록되지는 않는다.

## 실제 접속 검증

프로젝트 CA를 신뢰하는 Windows PC에서 새 요청으로 검사한다. 브라우저의 기존 SPA 화면·캐시·예전 데이터와 새 API 응답을 구분한다.

```powershell
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 10 -sS -i "https://192.168.3.30/api/health/ready"
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 10 -sS -o NUL -w "HTTP=%{http_code}\n" "https://192.168.3.30/admin"
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 10 -sS -o NUL -w "HTTP=%{http_code}\n" "https://192.168.3.30/api/admin/dashboard"
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 10 -sS -o NUL -w "HTTP=%{http_code}\n" "https://192.168.3.30/api/internal/privilege-violations"
```

- 공개 고객 웹·readiness 200, `status=ok`, `database=ok`.
- 공개 `/admin`, `/admin/`, `/admin/customers`, `/api/admin`, `/api/admin/`, `/api/admin/dashboard`, `/api/admin/monitoring-links` 모두 404. ADMIN 로그인 여부와 무관하다.
- 공개 내부 API 기존 차단 유지, 고객 계정 로그인·일반 업무·관제·자동화 회귀 검사.
- PC1·2·3에서 관리 전용 ADMIN 로그인·조회·새로고침 성공.
- 비허용·VPN 미연결 PC에서 `.7.178:9443` 새 연결 차단. 로그인 화면만 열리고 비밀번호를 요구하는 상태는 PC 접근 차단이 아니다.
- 실제 VPN 클라이언트에서 재연결 후 관리 주소 경로 수신·인증 확인.
- HAProxy 두 서버 UP 및 실제 서비스 출력을 기준으로 직접 NodePort와 8080·8443·11443 등 다른 입구의 우회 가능성 확인.

```bash
sudo k3s kubectl -n telecom get svc -o wide
```

NodePort 30444와 별도 API/Web 노출은 공개 Edge 규칙만으로 차단되지 않는다. TCP 연결 성공만으로 관리 데이터 노출을 판정하지 않으며, 익명 401만으로 ADMIN 계정의 우회를 배제하지 않는다. k3s 필수 통신을 확인하지 않고 호스트 방화벽 전체 차단을 적용하지 않는다. 증빙의 계정·쿠키·토큰은 가린다.

## 복구

```bash
sudo -v
python3 infrastructure/tools/k3s-admin-access.py status --work-dir "$loopGuardWork"
python3 infrastructure/tools/k3s-admin-access.py rollback --work-dir "$loopGuardWork"
```

이번 작업 직전 ConfigMap을 복원하고 공개 Edge를 순차 교체한다. 원본이 미차단이었다면 공개 관리자가 다시 열릴 수 있다. 동시 ConfigMap/Deployment 변경이 있으면 덮어쓰기를 거부한다. 복구 실패 시 작업 폴더를 보존하고 현재 Pod 상태부터 확인한다. `rollout undo`만으로 ConfigMap 원문이 복원되지 않는다.

2026-11-04 ZIP 도구의 기존 백업은 그때 사용한 `~/loop-public-admin-guard.py`와 기존 WORK_DIR로 관리한다. 현재 저장소 도구의 새 계획·포인터와 섞지 않는다.

## 재배포

[웹/API 클린 릴리스](webapi-clean-release.md)는 공개 ConfigMap과 양쪽 Edge의 네 관리자 차단·내부 API 차단·고객 upstream, 관리 Edge Ready, API ADMIN 보호를 배포 전후 검사한다. 정책이 다르면 배포를 멈춘다. 릴리스 검사는 Edge 정책을 자동 변경하지 않는다. 실제 사설 로그인·비허용 PC·VPN 시험은 별도로 기록한다.

현재 k3s 공개 Edge의 전체 YAML 사본은 저장소에 없으므로 예제 VLAN용 base를 현장에 통째로 적용하지 않는다. 운영 원문에서 차단 후보를 생성하는 이 도구와 배포 검사가 재현 가능한 정책 원본이다. 기존 `infrastructure/nginx/host-nginx.conf.example`과 로컬 Compose 공개 설정에도 같은 차단이 유지되어 있다.
