# 01 · 새 PC 설치 가이드

기준: Windows 11 + Docker Desktop(WSL2) + Git + Python 3.12 이상 + Node 22. 메모리 16GB 이상 권장(웹+관제 약 4.5GB, Wazuh 까지 약 8GB).
모든 명령은 **저장소 루트에서 PowerShell** 로 실행한다. 각 단계 끝의 **확인**이 통과해야 다음 단계로 간다.

| 단계 | 구성 | 학원 실습망에서의 위치 | 이 가이드의 재현 방식 | 본인 PC 검증 (2026-11-10) |
|---|---|---|---|---|
| 0 | 코드만 확인 | — | Python 가상환경 | ✅ 테스트 154개 통과, 시나리오 8/8 |
| 1 | 웹·API·DB | PC1·PC2 k3s + MySQL 8.4 복제 | Docker Compose 1대 | ✅ 고객 8443·관리자 8444 로그인, HTTP 시나리오 8/8 |
| 2 | Graylog·n8n | Graylog=PC1, n8n=PC2 Docker | Docker Compose 1대 | ✅ 브루트포스 전 구간 7/7(39.8초), EX-05 인시던트 등록(54.2초) |
| 3 | Wazuh | PC2 Docker | 공식 wazuh-docker single-node | ⬜ 명령·덧씌우기 파일까지 준비, 실행 결과 미기록 |
| 4 | pfSense | PC3 VM | VirtualBox VM (선택) | ⬜ 학원 설정 백업(비밀값 제거)과 구성 설명만 |

> 2026-11-10 에 처음부터 따라 하며 막힌 곳 5개를 고쳤다: 브라우저 로그인 403(nginx 가 포트를 뺌), 계정 브루트포스 탐지 규칙 없음, n8n 잠금 노드 요청 본문 오류, Graylog URL 허용 목록, n8n 버전. 아래 단계에 모두 반영돼 있다.

## 0. 준비

```powershell
git clone https://github.com/reereez15/loop-telecom-portfolio.git
cd loop-telecom-portfolio
python infrastructure/tools/prepare-local.py   # .env 와 .secrets/tls 를 무작위 값으로 생성 (둘 다 git 제외)
```

**확인 (Docker 없이)**
```powershell
cd backend; python -m venv .venv; .\.venv\Scripts\activate; pip install -r requirements.txt
python -m pytest -q                       # 154 passed
python ..\scripts\scenario_bruteforce.py  # 결과: 8/8 통과
deactivate; cd ..
```

`.env` 에서 직접 채울 값:

| 변수 | 넣을 값 |
|---|---|
| `AUTOMATION_API_TOKEN` | 비워 두면 `INCIDENT_API_TOKEN` 을 같이 씀 |
| `GRAYLOG_GELF_HOST` | 2단계를 띄우면 `graylog` |
| `GRAYLOG_PASSWORD_SECRET` | `python -c "import secrets;print(secrets.token_hex(32))"` 결과 |
| `GRAYLOG_ROOT_PASSWORD_SHA2` | `python -c "import hashlib,getpass;print(hashlib.sha256(getpass.getpass().encode()).hexdigest())"` 결과. 입력한 비밀번호는 `.secrets/graylog-admin.txt` 에 한 줄로 저장(시나리오 스크립트가 읽음, git 제외) |
| `N8N_IMAGE` | `n8nio/n8n:2.40.0` (기본값. 1.x 는 워크플로 활성화 실패) |
| `LOGIN_WINDOW_MINUTES` | 기본 `15`. 시연에서 복구 단계를 바로 보려면 `1` |
| `DISCORD_WEBHOOK_URL` | 본인 Discord 테스트 채널 웹훅 (없으면 비워 둠 — 알림 노드만 실패) |

hosts 파일(관리자 권한 메모장으로 `C:\Windows\System32\drivers\etc\hosts`)에 추가:

```
127.0.0.1 portal.telecom.test manage1.telecom.test
```

브라우저 경고를 없애려면 `.secrets/tls/ca.crt` 를 "신뢰할 수 있는 루트 인증 기관"에 등록한다(선택).

## 1. 웹·API·DB

```powershell
cd infrastructure/docker/compose/local
$f = "-f compose.yaml -f compose.portfolio.yaml --env-file ../../../../.env".Split(" ")
docker compose @f up -d mysql
docker compose @f --profile ops run --rm migrate
docker compose @f --profile ops run --rm migrate flask --app wsgi:app seed
docker compose @f --profile app up -d --build
cd ../../../..
```

| 접속 | 주소 | 계정 (시험 전용 고정값) |
|---|---|---|
| 고객 포털 | https://portal.telecom.test:8443 | `alice@test.local` / `Test1234!` (bob 도 같음) |
| 관리자 콘솔 | https://manage1.telecom.test:8444/admin | `admin@test.local` / `Test1234!` |

**확인**
```powershell
curl.exe -k https://localhost:8443/api/health/ready                                              # 200
curl.exe -k -o NUL -w "%{http_code}`n" https://localhost:8443/api/admin/dashboard               # 404 (고객 입구는 관리자 경로 차단)
python scripts/scenario_bruteforce.py --base-url https://localhost:8443 --admin-url https://localhost:8444 --ca .secrets/tls/ca.crt --wait-minutes 15
```
마지막 명령은 제한 창(15분)을 기다리므로 오래 걸린다. 시연용으로는 `.env` 에 `LOGIN_WINDOW_MINUTES=1` 을 넣고 `docker compose @f --profile app up -d api` 로 api 만 다시 띄운 뒤 `--wait-minutes 1` (약 80초, 결과 8/8).

팀 설정과 달라진 점:
- `compose.portfolio.yaml`: api 에 자동화 토큰·관리자 허용 목록·Graylog 주소·`LOGIN_WINDOW_MINUTES` 전달, 관리자 전용 입구 `127.0.0.1:8444` 추가, migrate 컨테이너에 시드 폴더 연결.
- `nginx.conf`·`nginx-admin.conf`: `proxy_set_header Host $http_host` — 포트(`:8443`)까지 넘겨야 Flask 의 같은 출처(Origin) 검사가 통과한다. 팀 설정(`$host`)대로면 **브라우저 로그인이 "허용되지 않은 출처의 요청입니다"(403)** 로 막힌다. 학원망은 443 이라 드러나지 않았다.

## 2. 관제: Graylog 6.1 + n8n 2.40

```powershell
python scripts/localize_monitoring.py      # 학원망 주소 → 로컬 주소, 비밀값 자리 → 환경변수 (monitoring/local/ 에 사본 생성)
docker compose -f monitoring/compose/monitoring.compose.yaml --env-file .env up -d
```

| 접속 | 주소 | 비고 |
|---|---|---|
| Graylog | http://localhost:9000 | `admin` / 0단계에서 정한 비밀번호 |
| GELF 입력 | UDP `127.0.0.1:12201` | 앱·시험 스크립트가 로그를 보내는 곳 |
| n8n | http://localhost:5678 | 처음 접속 시 소유자 계정 생성 (이메일·비밀번호는 `.secrets/n8n-owner.txt` 에 적어 둠, git 제외) |

기본 설정 (순서대로):
1. **Graylog 입력**: System → Inputs → `GELF UDP` → Launch, Bind address `0.0.0.0`, Port `12201`.
2. **콘텐츠 팩**: System → Content Packs → Upload → `monitoring/local/graylog/Graylog_Wazuh분할.json` → Install. (팀 탐지 규칙 19개 + n8n 알림 10개. 알림 주소는 `http://n8n:5678/webhook/...` 로 바뀌어 있음)
3. **URL 허용 목록**: System → Configurations → URL Whitelist 에 정규식 `^http://n8n:5678/webhook/.*$` 추가. 없으면 Graylog 로그에 `URL ... is not whitelisted` 가 남고 n8n 이 호출되지 않는다.
4. **앱 로그용 계정 브루트포스 규칙(본인 추가)**:
   ```powershell
   python scripts/graylog_add_account_bruteforce.py --password-file .secrets/graylog-admin.txt
   # 규칙 생성: ED-A1 | 계정 브루트포스(앱 로그) (실패 ≥ 5 / 15분, 1분마다 검사)
   ```
   팀 ED-08 은 모의 로그의 `username` 을 세는데, 앱은 이메일 대신 `account_hash` 를 남겨서 앱 로그에는 걸리지 않는다. 이 규칙이 그 빈자리를 채운다.
5. **n8n 워크플로**: Workflows → Import from File → `monitoring/local/n8n/n8n_경로_실사용URL_적용.json` → Save → **Publish**(2.x 의 활성화).
   - n8n **2.40.0 이상** 필요. 워크플로가 `httpRequest 4.5`·`set 3.5` 노드를 써서 1.x 에서는 활성화 단계에서 `Cannot read properties of undefined` 오류가 난다.
   - 본인이 고친 것: 앱 API 를 부르는 노드 10개 본문 식의 `}}` 가 n8n 식(`{{ … }}`)을 중간에서 닫던 문제(`} }` 로 띄어 씀)와 꺼져 있던 노드 켜기, `8- 브루트포스 계정잠금` 이 `account_hash` 를 받아 잠그도록 판정·요청 노드 수정.
6. 앱 로그를 Graylog 로 보내려면 `.env` 에 `GRAYLOG_GELF_HOST=graylog` 를 넣고 1단계 `up -d` 를 다시 실행.

**확인** (시나리오 문서 [02](02_SCENARIOS.md) 와 같음)
```powershell
python scripts/scenario_ex05_sqli.py                 # 약 1분 → 인시던트 #N 'ED-EX-05 | SQL Injection 의심' high OPEN
python scripts/scenario_bruteforce_e2e.py --register --victim s-a1-01@test.local --wait-minutes 1 --graylog-password-file .secrets/graylog-admin.txt
                                                     # 7/7 통과 · 탐지까지 약 40~60초
```

## 3. Wazuh 4.9 (single-node)

팀 저장소에는 Wazuh 실행 정의가 없고 규칙 파일(`monitoring/wazuh/local_rules.xml`, `local_decoder.xml`)만 있다. 공식 Docker 구성을 쓰되, 포트를 내 PC 안에서만 열도록 덧씌우기 파일을 같이 쓴다.

```powershell
git clone https://github.com/wazuh/wazuh-docker.git -b v4.9.2 ..\wazuh-docker
cd ..\wazuh-docker\single-node
docker compose -f generate-indexer-certs.yml run --rm generator
docker compose -f docker-compose.yml -f ..\..\loop-telecom-portfolio\monitoring\wazuh\compose.localhost.yaml up -d
docker cp ..\..\loop-telecom-portfolio\monitoring\wazuh\local_rules.xml single-node-wazuh.manager-1:/var/ossec/etc/rules/local_rules.xml
docker cp ..\..\loop-telecom-portfolio\monitoring\wazuh\local_decoder.xml single-node-wazuh.manager-1:/var/ossec/etc/decoders/local_decoder.xml
# docker cp 로 넣은 파일은 root 소유라 manager 가 못 읽을 수 있다 → 소유자·권한을 맞춘다
docker exec single-node-wazuh.manager-1 bash -c "chown wazuh:wazuh /var/ossec/etc/rules/local_rules.xml /var/ossec/etc/decoders/local_decoder.xml && chmod 660 /var/ossec/etc/rules/local_rules.xml /var/ossec/etc/decoders/local_decoder.xml"
# 재시작 전에 규칙 문법 검사 — 오류가 있으면 재시작 후 manager 가 뜨지 않는다
docker exec single-node-wazuh.manager-1 /var/ossec/bin/wazuh-analysisd -t
docker exec single-node-wazuh.manager-1 /var/ossec/bin/wazuh-control restart
cd ..\..\loop-telecom-portfolio
```
> ⚠ `docker compose down -v` 는 쓰지 않는다. 볼륨이 지워지면 에이전트 등록·규칙·인증서가 모두 사라진다. 끌 때는 `down` 만.

| 접속 | 주소 |
|---|---|
| Wazuh 대시보드 | https://localhost (기본 계정은 wazuh-docker 문서 참고 — 첫 로그인 후 변경) |
| 에이전트 → 매니저 | TCP `127.0.0.1:1514` / 등록 `1515` |

**확인**: `docker exec -it single-node-wazuh.manager-1 /var/ossec/bin/wazuh-logtest` 에 `monitoring/graylog/attack-test/PC1_to_PC1/Wazuh/Wazuh_실제룰엔진_logtest_보조.txt` 의 로그 줄을 넣어 규칙 100230~100237 이 걸리는지 본다.
※ 컨테이너 이름은 `docker ps` 로 확인. 443 이 다른 프로그램과 겹치면 `compose.localhost.yaml` 에서 `127.0.0.1:8445:5601` 처럼 바꾼다.
※ 학원망의 매니저 `ossec.conf`·에이전트 설정은 팀원 PC2 에만 있고 저장소에 없다(아래 '팀 PC 에만 있던 설정').
※ 대시보드·`alerts.json` 의 `timestamp` 는 UTC 로 저장될 수 있다. KST 로 보이는 컨테이너 로그와 비교할 때 +9시간을 맞춰 본다.

### 3-1. Wazuh 경보를 Graylog 로 (미검증 — 순서만 정리)

팀 Graylog 규칙 `ED-07`(100211·100220~100222)·`ED-WZ-02`(100230~100237)는 `wazuh_rule_id` 필드를 찾는다. 이 필드는 Wazuh 가 만들지 않고 **Graylog 파이프라인이 만들어야** 하는데, 그 설정이 팀 저장소에 없었다.

1. Graylog: System → Inputs → `Syslog UDP` (또는 `Raw/Plaintext UDP`) 포트 `5140` 추가. Docker 로 띄웠다면 `monitoring.compose.yaml` 의 graylog `ports` 에 `127.0.0.1:5140:5140/udp` 추가.
2. Wazuh manager `ossec.conf` 에 JSON 경보 전송 추가 후 `wazuh-control restart`:
   ```xml
   <syslog_output>
     <server>graylog 주소(같은 Docker 망이면 graylog 컨테이너 IP)</server>
     <port>5140</port>
     <format>json</format>
     <level>5</level>
   </syslog_output>
   ```
   ※ 컨테이너 안에서 `localhost` 는 자기 자신이다. 다른 컨테이너는 서비스 이름이나 IP, 내 PC 는 `host.docker.internal`.
3. 파이프라인 규칙 [`monitoring/graylog/pipelines/wazuh_alert_parse.rule`](../../monitoring/graylog/pipelines/wazuh_alert_parse.rule) 을 붙여 넣고 파이프라인 `Wazuh 경보` 를 **스트림에 연결**한다. 연결을 빠뜨리면 메시지는 들어와도 필드가 안 생겨 규칙이 `Never` 로 남는다.
4. 확인: Graylog 검색 `_exists_:wazuh_rule_id` → 결과가 있으면 `ED-07`·`ED-WZ-02` 가 동작할 수 있는 상태.

## 4. pfSense (선택)

학원 PC3 에서 담당 정동석 님이 구성했다. 설정 백업(비밀값 21개 제거)과 구성 설명: [`security/pfsense/`](../../security/pfsense/README.md)
백업에는 키·인증서가 없어 **그대로 복원하면 VPN·웹 관리 화면이 동작하지 않는다.** 새로 세울 때는 백업의 값을 보고 손으로 만든다.

1. pfSense CE 2.7 ISO, VirtualBox VM: 메모리 1GB, NIC1=NAT(WAN), NIC2=Host-only(LAN `192.168.56.0/24`).
2. 설치 후 LAN 주소 `192.168.56.1`, 웹 설정 `https://192.168.56.1`, 관리자 비밀번호 즉시 변경.
3. 망 분리: README 1절 표대로 VLAN 10/20/30/40 (DMZ·WAS·DB·SEC). 각 구간 규칙은 '자기 구간 → pfSense DNS 허용', '→ 관리망 차단(로그)' 두 개.
4. 외부 공개: README 2절 NAT 표. 고객용 HTTPS 만 열고 관리자 웹(9443)은 팀 PC 별칭·VPN 대역에서만.
5. 로그 전송: Status → System Logs → Settings → Remote log servers. 학원망은 `192.168.7.100:5514`. 로컬 Graylog 는 `127.0.0.1` 에만 열려 있으므로 VM 에서 보내려면 `monitoring.compose.yaml` 의 `127.0.0.1:1514:1514/udp` 를 `192.168.56.1:1514:1514/udp` 로 바꾸고 Graylog 에 `Syslog UDP 1514` 입력을 추가한다.

## 팀 PC 에만 있던 설정 (점검 결과)

| 항목 | 팀 저장소 상태 | 이 저장소에서 |
|---|---|---|
| `.env` 값 (토큰·DB 비밀번호) | 각자 PC | `prepare-local.py` 가 무작위 생성, 빠져 있던 8개 변수를 `.env.example` 에 추가 |
| Graylog·n8n 실행 정의 | 없음 (PC1·PC2 에서 직접 실행) | `monitoring/compose/monitoring.compose.yaml` |
| Graylog URL 허용 목록 | PC1 Graylog 화면에서만 설정 | 2단계 3번에 명시 |
| 앱 로그용 브루트포스 규칙 | 없음 | `scripts/graylog_add_account_bruteforce.py` |
| n8n 버전 | PC2 에 설치된 버전에 맞춘 워크플로 | `N8N_IMAGE=n8nio/n8n:2.40.0` 고정 |
| n8n 자격 증명(토큰·웹훅) | 워크플로 JSON 안에 값이 그대로 | `{{ $env.… }}` 로 바꾸고 기록 전체에서 제거 |
| 관리자 입구 | k3s NodePort 30444 + pfSense NAT | 로컬 `127.0.0.1:8444` (`compose.portfolio.yaml`) |
| nginx Host 헤더 | 443 전제(`$host`) | `$http_host` (로컬 8443/8444 에서 로그인되게) |
| Wazuh 실행 정의·`ossec.conf` | PC2 에만 | 공식 single-node + `monitoring/wazuh/compose.localhost.yaml`. **`ossec.conf` 는 아직 받지 못함** |
| Wazuh → Graylog 파이프라인(`wazuh_rule_id` 필드) | PC1 Graylog 화면에서만 | `monitoring/graylog/pipelines/wazuh_alert_parse.rule` + 3-1 절 (미검증) |
| pfSense 설정 | PC3 에만 | `security/pfsense/config.sanitized.xml` (비밀값 제거) |
| k3s 매니페스트·MySQL 복제 | 저장소에 있음 (`infrastructure/`) | 노트북 재현은 Compose 1대로 대체 |

## 포트 정리

| 포트 | 구성 | 이 가이드 | 학원망 |
|---|---|---|---|
| 8443/tcp | 고객용 HTTPS 입구 | 127.0.0.1 | PC3 HAProxy 443 → 두 웹 노드 |
| 8444/tcp | 관리자 입구 | 127.0.0.1 | 관리 전용 9443 (팀 PC·VPN) |
| 5000/tcp | Flask API | 컨테이너 내부만 | 클러스터 내부 |
| 3306/tcp | MySQL | 컨테이너 내부만 | PC2 Primary → PC1 Replica (GTID+TLS) |
| 9000/tcp | Graylog UI | 127.0.0.1 | PC1 |
| 12201/udp | GELF 입력 | 127.0.0.1 | PC1 |
| 1514/udp | Syslog 입력(Graylog) | 127.0.0.1 | PC1 (pfSense 는 5514) |
| 5678/tcp | n8n | 127.0.0.1 | PC2 |
| 443/tcp, 1514-1515/tcp, 55000/tcp | Wazuh 대시보드·에이전트·API | 127.0.0.1 | PC2 |

## 끄기와 초기화

```powershell
docker compose -f monitoring/compose/monitoring.compose.yaml down
cd infrastructure/docker/compose/local; docker compose -f compose.yaml -f compose.portfolio.yaml --profile app down; cd ../../../..
# 데이터까지 지우려면 down -v (DB·Graylog·n8n 기록 삭제 → 2단계 설정을 다시 해야 함)
```

## 자주 막히는 곳

| 증상 | 원인 | 해결 |
|---|---|---|
| `Run infrastructure/tools/prepare-local.py first` | `.env` 없음 | 0단계 실행 |
| 브라우저 로그인 "허용되지 않은 출처의 요청입니다" | nginx 가 Host 에서 포트를 뺌 | 저장소 최신 `nginx*.conf`(`$http_host`) 확인 후 `docker restart telecom-local-edge-1 telecom-local-admin-edge-1` |
| 로그인 후 바로 로그아웃 | `__Host-` 쿠키는 HTTPS 전용 | 8080 이 아니라 8443 으로 접속 |
| 관리자 화면 404 | 고객 입구(8443)는 관리자 경로 차단 | 8444 사용 |
| `failed to execute bake` (`--build` 할 때) | Docker Compose 5.x 의 bake 빌드 오류 | 이미지만 직접 빌드: `cd backend; docker build -t telecom-local-api -f ..\infrastructure\docker\backend\Dockerfile .` → `up -d --no-build api` |
| 시나리오 5-1·5-3 이 429 | 로그인 제한 창이 아직 남음 | `--wait-minutes` 를 api 의 `LOGIN_WINDOW_MINUTES` 와 같게 |
| 전 구간 시나리오 4단계 FAIL, 탐지는 PASS | 같은 계정 재시험(알림 유예 15분) 또는 n8n 워크플로 미게시 | `--victim` 이름 바꾸기 / n8n Publish 확인 |
| `network telecom-local_default not found` | 앱을 먼저 안 띄움 | 1단계 후 2단계 |
| OpenSearch 재시작 반복 | WSL 메모리 부족 / `vm.max_map_count` | `wsl -d docker-desktop sysctl -w vm.max_map_count=262144` |
| n8n 노드 401 | 토큰 불일치 | `.env` 의 `AUTOMATION_API_TOKEN` 과 api 컨테이너 값이 같은지 확인 후 둘 다 재시작 |
| n8n 실행이 모두 'Error' | Discord 웹훅 비어 있음 (마지막 노드만 실패) | 정상. 알림까지 보려면 `DISCORD_WEBHOOK_URL` 설정 |
