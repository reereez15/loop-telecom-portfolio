# pfSense (PC3 · `c-pfsense.telecom.test`)

학원망 프로젝트에서 쓴 pfSense 23.3 설정 백업(2026-11-06)을 비밀값을 지우고 남긴 것.

- 파일: [`config.sanitized.xml`](config.sanitized.xml)
- 만든 방법: `python scripts/sanitize_pfsense.py <원본 config.xml> security/pfsense/config.sanitized.xml`
- 지운 값 21개: 계정 비밀번호 해시 2, 인증서 5·개인키 4, OpenVPN TLS 키 1, SSH 호스트 키 4, SNMP 커뮤니티 1, Suricata 견본 파일 4(비밀 아님, 길이만 줄임)
- 남긴 값: 인터페이스·별칭·방화벽·NAT·OpenVPN·Suricata·HAProxy 설정, 학원 내부 사설 IP
- **이 파일은 복원용이 아니다.** 키·인증서가 빠져 있어 그대로 올리면 VPN·웹 관리 화면이 동작하지 않는다.

## 1. 망 분리

| 인터페이스 | 이름 | 장치 | 주소 | 용도 |
|---|---|---|---|---|
| wan | WAN | em0 | DHCP (학원망 192.168.3.0/24) | 외부(학원망) |
| lan | LAN | em1 | 192.168.50.1/24 | 관리망 `MGMT_NET` |
| opt1 | DMZ | em2.10 (VLAN 10) | 192.168.10.1/24 | 웹 공개 구간 (`WEB_VIP` .100 예정) |
| opt2 | WAS | em2.20 (VLAN 20) | 192.168.20.1/24 | WAS·k3s 노드 |
| opt3 | DB | em2.30 (VLAN 30) | 192.168.30.1/24 | DB (`DB_VIP` .100 예정) |
| opt4 | SEC | em2.40 (VLAN 40) | 192.168.40.1/24 | 보안 관제 |

DMZ·WAS·DB·SEC 네 구간은 같은 규칙 두 개만 갖는다.

1. 자기 구간 → pfSense DNS(53) **허용**
2. 자기 구간 → 관리망(`MGMT_NET`) **차단**(로그 남김)

그 밖의 트래픽은 pfSense 기본 정책(명시 허용이 없으면 차단)으로 막힌다. 그래서 구간 사이 통신은 지금 DNS 말고는 모두 닫혀 있다.

## 2. 외부 공개와 관리자 접근 (NAT 포트 포워딩)

서비스 본체는 PC1 VM의 k3s(`192.168.7.185`) NodePort 에서 돈다.

| 들어오는 곳 | 출발지 | → 내부 | 설명 |
|---|---|---|---|
| WAN `:8080` | any | `192.168.7.185:30080` | 웹(HTTP) |
| WAN `:8443` | any | `192.168.7.185:30443` | 웹(HTTPS) |
| WAN `:9443` | `ADMIN_PCS`(PC1·2·3) | `192.168.7.185:30444` | **관리자 웹** — 팀 PC 3대만 |
| OpenVPN `192.168.7.178:9443` | `ADMIN_VPN_NET`(10.0.0.0/24) | `192.168.7.185:30444` | **관리자 웹** — VPN 인증 사용자만 |
| `192.168.3.30:9000` | `LOOP_MONITOR_CLIENTS` | `192.168.3.18:9000` | Graylog(PC1) |
| `192.168.3.30:9443` | `LOOP_MONITOR_CLIENTS` | `192.168.3.19:443` | Wazuh 대시보드(PC2) |
| `192.168.3.30:10443` | `192.168.3.19`(PC2) | `192.168.7.185:30445` | n8n → 앱 자동화 API 전용 입구 |

- 관리자 웹은 **고객 입구와 포트·출발지를 분리**했다(고객 8443 / 관리자 9443은 팀 PC와 VPN만). 앱 쪽 `/api/admin` 차단(고객 입구 404)과 짝을 이룬다.
- 아웃바운드 NAT 는 hybrid. 같은 학원망 안에서 들어온 요청이 응답 경로가 꼬이지 않도록 SNAT(`telecom-web-return`, `*-SNAT`)을 따로 두었다.

## 3. HAProxy (pfSense 패키지) — 웹 이중화

| 프런트엔드 | 바인드 | 형식 | 백엔드 |
|---|---|---|---|
| `telecom-public-https` | 192.168.3.30:443 | TCP | `telecom-public-nodes` |
| `telecom-public-test` | 192.168.3.30:11443 | TCP | `telecom-public-proxy-test` |
| `telecom-http-redirect` | 192.168.3.30:80 | HTTP | `https://192.168.3.30` 로 302 |

`telecom-public-nodes`: PC1(`192.168.7.185:30443`)·PC2(`192.168.7.100:30443`) 라운드로빈, HTTP 헬스체크, `option redispatch` 로 한 대가 죽으면 다른 노드로 넘긴다.

## 4. 관리자 VPN (OpenVPN)

- `TelecomLab-Admin-VPN`: UDP 1194, **인증서 + 로컬 계정(server_tls_user)**, TLS auth 키, `strictusercn`
- 터널 10.0.0.0/24, 최대 4명, 푸시 경로는 pfSense 관리 IP·관리자 웹 IP 두 개만(`192.168.50.1/32`, `192.168.7.178/32`) — 전체 망을 열지 않는다
- 암호: AES-256-GCM / AES-128-GCM / CHACHA20-POLY1305, SHA256
- 예전 규칙(`LEGACY-disabled-VPN-pfSense-443`)은 지우지 않고 비활성화해 기록으로 남겼다

## 5. Suricata (IDS)

- LAN 인터페이스 `C_IDS_LAN`, 규칙 묶음 22개(app-layer·dns·http·tls·smb 등 이벤트 규칙), EVE 로그 켬
- 모드는 IPS(legacy) 이지만 `blockoffenders=off` → **탐지만 하고 차단하지 않음**
- 직접 만든 규칙 1개 → [`../suricata/rules/custom.rules`](../suricata/rules/custom.rules)

## 6. 로그

- 원격 syslog `192.168.7.100:5514`(rfc3164), 설정 변경 로그 켬 → Graylog 로 수집
- 차단 규칙은 대부분 `log` 를 켜 두어 탐지 근거로 쓴다

## 보완할 점 (회고용)

- LAN 기본 규칙 `Default allow LAN to any` 가 그대로다. 관리망이라도 필요한 목적지만 여는 편이 낫다.
- SNMP 커뮤니티가 기본값이었다(백업에서는 지움). 쓰지 않으면 끄고, 쓰면 바꾼다.
- Suricata 는 탐지만 한다. 오탐을 확인한 뒤 일부 규칙만 차단으로 바꾸는 단계가 남아 있다.
- 시험용 규칙(`LOOP_KALI_ICMP_TEST`, `telecom-haproxy-test-11443`)이 운영 규칙과 섞여 있다. 시험이 끝나면 지우거나 별도 구분선(separator)으로 묶는다.
