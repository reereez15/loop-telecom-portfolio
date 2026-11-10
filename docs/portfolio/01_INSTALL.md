# 01 · 새 PC 설치 가이드

기준: Windows 11 + Docker Desktop(WSL2) + Git + Python 3.12 + Node 22. 메모리 16GB 이상 권장(관제 스택 포함 시 약 6GB 사용).
모든 명령은 저장소 루트에서 PowerShell로 실행합니다. 각 단계 끝의 **확인**이 통과해야 다음 단계로 갑니다.

| 단계 | 구성 | 학원 실습망에서의 위치 | 이 가이드의 재현 방식 | 검증 상태 |
|---|---|---|---|---|
| 0 | 코드만 확인 | — | Python 가상환경 | ✅ 2026-11-10 실행 확인 (테스트 150개, 시나리오 8/8) |
| 1 | 웹·API·DB | PC1·PC2 k3s + MySQL 8.4 복제 | Docker Compose 1대 | ⬜ 본인 PC에서 확인 후 체크 |
| 2 | Graylog·n8n | Graylog=PC1, n8n=PC2 Docker | Docker Compose 1대 | ⬜ |
| 3 | Wazuh | PC2 Docker | 공식 wazuh-docker single-node | ⬜ |
| 4 | pfSense | PC3 VM | VirtualBox VM (선택) | ⬜ |

## 0. 준비

```powershell
git clone https://github.com/reereez15/loop-telecom-portfolio.git
cd loop-telecom-portfolio
python infrastructure/tools/prepare-local.py   # .env 와 .secrets/tls 를 무작위 값으로 생성 (둘 다 git 제외)
```

`.env`에서 직접 채울 값:

| 변수 | 넣을 값 |
|---|---|
| `AUTOMATION_API_TOKEN` | 비워 두면 `INCIDENT_API_TOKEN`을 같이 씀 |
| `GRAYLOG_GELF_HOST` | 2단계를 띄우면 `graylog` |
| `GRAYLOG_PASSWORD_SECRET` | `python -c "import secrets;print(secrets.token_hex(32))"` 결과 |
| `GRAYLOG_ROOT_PASSWORD_SHA2` | `python -c "import hashlib,getpass;print(hashlib.sha256(getpass.getpass().encode()).hexdigest())"` 결과 |
| `DISCORD_WEBHOOK_URL` | 본인 Discord 테스트 채널의 웹훅 (없으면 비워 둠 — 알림만 실패) |

hosts 파일(관리자 권한 메모장으로 `C:\Windows\System32\drivers\etc\hosts`)에 추가:

```
127.0.0.1 portal.telecom.test manage1.telecom.test
```

브라우저 경고를 없애려면 `.secrets/tls/ca.crt`를 "신뢰할 수 있는 루트 인증 기관"에 등록합니다(선택).

## 1. 웹·API·DB

```powershell
cd infrastructure/docker/compose/local
docker compose -f compose.yaml -f compose.portfolio.yaml --env-file ../../../../.env up -d mysql
docker compose -f compose.yaml -f compose.portfolio.yaml --env-file ../../../../.env --profile ops run --rm migrate
docker compose -f compose.yaml -f compose.portfolio.yaml --env-file ../../../../.env --profile ops run --rm migrate flask --app wsgi:app seed
docker compose -f compose.yaml -f compose.portfolio.yaml --env-file ../../../../.env --profile app up -d --build
cd ../../../..
```

| 접속 | 주소 | 계정 |
|---|---|---|
| 고객 포털 | https://portal.telecom.test:8443 | `alice@test.local` / `Test1234!` |
| 관리자 콘솔 | https://manage1.telecom.test:8444/admin | `admin@test.local` / `Test1234!` |

**확인**
```powershell
curl.exe -k https://localhost:8443/api/health/ready      # HTTP 200
curl.exe -k -o NUL -w "%{http_code}" https://localhost:8443/api/admin/dashboard   # 404 (고객 입구는 관리자 경로 차단)
python scripts/scenario_bruteforce.py --base-url https://localhost:8443 --admin-url https://localhost:8444 --ca .secrets/tls/ca.crt --out docs/portfolio/evidence/S-A1_http.json
```

팀 설정과 달라진 점(`compose.portfolio.yaml`): api에 자동화 토큰·관리자 허용 목록·Graylog 주소 전달, 관리자 전용 입구 `127.0.0.1:8444` 추가, migrate 컨테이너에 시드 폴더 연결.

## 2. 관제: Graylog 6.1 + n8n

```powershell
python scripts/localize_monitoring.py      # 학원망 주소 → 로컬 주소, 비밀값 자리 → 환경변수 (monitoring/local/ 에 사본 생성)
docker compose -f monitoring/compose/monitoring.compose.yaml --env-file .env up -d
```

| 접속 | 주소 | 비고 |
|---|---|---|
| Graylog | http://localhost:9000 | `admin` / 0단계에서 정한 비밀번호 |
| GELF 입력 | UDP `127.0.0.1:12201` | 앱·시험 스크립트가 로그를 보내는 곳 |
| n8n | http://localhost:5678 | 처음 접속 시 소유자 계정 생성 |

기본 설정:
1. **Graylog 입력 만들기**: System → Inputs → `GELF UDP` → Launch, Bind address `0.0.0.0`, Port `12201`.
2. **콘텐츠 팩 설치**: System → Content Packs → Upload → `monitoring/local/graylog/Graylog_Wazuh분할.json` → Install. (탐지 규칙 18개 + n8n 알림. 알림 주소는 `http://n8n:5678/webhook/...`로 바뀌어 있음)
3. **n8n 워크플로 가져오기**: Workflows → Import from File → `monitoring/local/n8n/n8n_경로_실사용URL_적용.json` → 저장 → Active 켜기.
4. 앱 로그를 Graylog로 보내려면 `.env`에 `GRAYLOG_GELF_HOST=graylog`를 넣고 1단계의 마지막 `up -d` 를 다시 실행.

**확인**
```powershell
# 모의 로그 1건 (학원 시험 스크립트와 같은 형식, 주소만 로컬)
$u=[Net.Sockets.UdpClient]::new(); $b=[Text.Encoding]::UTF8.GetBytes('{"version":"1.1","host":"local-test","short_message":"[SIMULATED] EX-05","_rule":"sqli-detected","_src_ip":"198.51.100.41","_test_case":"EX-05_SQLInjection"}'); [void]$u.Send($b,$b.Length,'127.0.0.1',12201); $u.Dispose()
```
Graylog Search에 `test_case:EX-05_SQLInjection` 1건 → Alerts에 `ED-EX-05` → n8n Executions 1건 → 관리자 콘솔 보안 인시던트 목록에 1건.

## 3. Wazuh (선택, 4.x single-node)

팀 저장소에는 Wazuh 실행 정의가 없고 규칙 파일만 있습니다. 공식 Docker 구성을 사용합니다.

```powershell
git clone https://github.com/wazuh/wazuh-docker.git -b v4.9.2 ..\wazuh-docker
cd ..\wazuh-docker\single-node
docker compose -f generate-indexer-certs.yml run --rm generator
docker compose up -d
docker cp ..\..\loop-telecom-portfolio\monitoring\wazuh\local_rules.xml single-node-wazuh.manager-1:/var/ossec/etc/rules/local_rules.xml
docker cp ..\..\loop-telecom-portfolio\monitoring\wazuh\local_decoder.xml single-node-wazuh.manager-1:/var/ossec/etc/decoders/local_decoder.xml
docker exec single-node-wazuh.manager-1 /var/ossec/bin/wazuh-control restart
```
| 접속 | 주소 |
|---|---|
| Wazuh 대시보드 | https://localhost (기본 계정은 wazuh-docker 문서 참고, 첫 로그인 후 변경) |
| 에이전트 → 매니저 | TCP 1514 / 등록 1515 |

**확인**: `docker exec -it single-node-wazuh.manager-1 /var/ossec/bin/wazuh-logtest` 에 `monitoring/graylog/attack-test/PC1_to_PC1/Wazuh/Wazuh_실제룰엔진_logtest_보조.txt`의 로그 줄을 넣어 규칙 100230~100237이 걸리는지 확인.
※ 컨테이너 이름은 `docker ps`로 확인. 포트 443·1514가 다른 프로그램과 겹치면 compose 파일에서 바꿉니다.

## 4. pfSense (선택)

학원 PC3에서 담당 정동석 님이 구성했습니다. 재현은 VirtualBox VM으로 합니다.
1. pfSense CE 2.7 ISO, VM: 메모리 1GB, NIC1=NAT(WAN), NIC2=Host-only(LAN 192.168.56.0/24).
2. 설치 후 LAN 주소 `192.168.56.1`, 웹 설정 https://192.168.56.1.
3. 방화벽 규칙: 팀 문서 `network/port-matrix.md`, `security/` 폴더 기준. 고객용 443만 허용, 관리 접속은 VPN·내부망만.
4. Graylog로 로그 전송: Status → System Logs → Settings → Remote log servers `호스트IP:1514`, Graylog에 `Syslog UDP 1514` 입력 추가.

## 포트 정리

| 포트 | 구성 | 이 가이드 | 학원망 |
|---|---|---|---|
| 8443/tcp | 고객용 HTTPS 입구 | 127.0.0.1 | PC3 HAProxy 443 → 두 웹 노드 |
| 8444/tcp | 관리자 입구 | 127.0.0.1 | 내부망·VPN 전용 관리 주소 |
| 5000/tcp | Flask API | 컨테이너 내부만 | 클러스터 내부 |
| 3306/tcp | MySQL | 컨테이너 내부만 | PC2 Primary → PC1 Replica (GTID+TLS) |
| 9000/tcp | Graylog UI | 127.0.0.1 | PC1 |
| 12201/udp | GELF 입력 | 127.0.0.1 | PC1 |
| 1514/udp | Syslog 입력(Graylog) | 127.0.0.1 | PC1 |
| 5678/tcp | n8n | 127.0.0.1 | PC2 |
| 443/tcp, 1514-1515/tcp | Wazuh 대시보드·에이전트 | localhost | PC2 |

## 끄기와 초기화

```powershell
docker compose -f monitoring/compose/monitoring.compose.yaml down
cd infrastructure/docker/compose/local; docker compose -f compose.yaml -f compose.portfolio.yaml --profile app down
# 데이터까지 지우려면 down -v (DB·Graylog 기록 삭제)
```

## 자주 막히는 곳

| 증상 | 원인 | 해결 |
|---|---|---|
| `Run infrastructure/tools/prepare-local.py first` | `.env` 없음 | 0단계 실행 |
| 로그인 후 바로 로그아웃 | `__Host-` 쿠키는 HTTPS 전용 | 8080이 아니라 8443으로 접속 |
| 관리자 화면 404 | 고객 입구(8443)는 관리자 경로 차단 | 8444 사용 |
| `network telecom-local_default not found` | 앱을 먼저 안 띄움 | 1단계 후 2단계 |
| OpenSearch 재시작 반복 | WSL 메모리 부족 / `vm.max_map_count` | `wsl -d docker-desktop sysctl -w vm.max_map_count=262144` |
| n8n 알림 401 | 토큰 불일치 | `.env`의 `AUTOMATION_API_TOKEN` 과 api 컨테이너 값이 같은지 확인 후 둘 다 재시작 |
