"""관제 스택(Graylog·n8n) 기본 설정을 한 번에 — 김준식

설치 가이드 2단계에서 화면으로 하던 7가지를 대신한다. 여러 번 실행해도 안전하다(이미 된 것은 건너뜀).
  1) Graylog GELF UDP 12201 입력
  2) Graylog 콘텐츠 팩 설치 (팀 탐지 규칙 19 + n8n 알림 10, 김준오)
  3) Graylog URL 허용 목록 ^http://n8n:5678/webhook/.*$
  4) Graylog 앱 로그용 계정 브루트포스 규칙 ED-A1
  5) n8n 소유자 계정 (처음 한 번, 무작위 비밀번호 → .secrets/n8n-owner.txt)
  6) n8n 워크플로 가져오기 (로컬 재현 수정본)
  7) n8n 워크플로 활성화(Publish)

  docker compose -f monitoring/compose/monitoring.compose.yaml --env-file .env up -d
  python scripts/setup_monitoring.py
"""
import json
import secrets
import sys
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
GRAYLOG = "http://localhost:9000/api"
N8N = "http://localhost:5678"
PACK = ROOT / "monitoring/local/graylog/Graylog_Wazuh분할.json"
WORKFLOW = ROOT / "monitoring/local/n8n/portfolio/n8n_경로_실사용URL_적용_로컬재현.json"
WHITELIST = r"^http://n8n:5678/webhook/.*$"
OWNER_FILE = ROOT / ".secrets/n8n-owner.txt"


def wait(name, fn, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if fn():
                print(f"   {name} 준비됨 ({round(time.time() - start)}초)")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    sys.exit(f"{name} 가 {timeout}초 안에 준비되지 않았습니다. docker ps 로 컨테이너 상태를 확인하세요.")


def setup_graylog():
    pw_file = ROOT / ".secrets/graylog-admin.txt"
    if not pw_file.exists():
        sys.exit(".secrets/graylog-admin.txt 가 없습니다. python scripts/setup_portfolio_env.py 를 먼저 실행하세요.")
    g = requests.Session()
    g.auth = ("admin", pw_file.read_text(encoding="utf-8").strip())
    g.headers.update({"X-Requested-By": "setup_monitoring", "Accept": "application/json"})
    print("[Graylog]")
    # /system/lbstatus 는 text/plain 이라 Accept: json 이면 406 → 로그인까지 되는 /system 으로 확인
    wait("Graylog", lambda: g.get(f"{GRAYLOG}/system", timeout=5).status_code == 200)

    # 1) GELF 입력
    if any(i["type"].endswith("GELFUDPInput") for i in g.get(f"{GRAYLOG}/system/inputs").json()["inputs"]):
        print(" 1) GELF UDP 입력: 이미 있음")
    else:
        r = g.post(f"{GRAYLOG}/system/inputs", json={
            "title": "GELF UDP 12201", "type": "org.graylog2.inputs.gelf.udp.GELFUDPInput", "global": True,
            "configuration": {"bind_address": "0.0.0.0", "port": 12201, "recv_buffer_size": 262144,
                              "number_worker_threads": 2, "decompress_size_limit": 8388608}})
        r.raise_for_status()
        print(" 1) GELF UDP 입력: 만듦")

    # 2) 콘텐츠 팩
    if not PACK.exists():
        import localize_monitoring
        localize_monitoring.main()
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    pid, rev = pack["id"], pack["rev"]
    if g.get(f"{GRAYLOG}/system/content_packs/{pid}").status_code != 200:
        g.post(f"{GRAYLOG}/system/content_packs", json=pack).raise_for_status()
    if g.get(f"{GRAYLOG}/system/content_packs/{pid}/installations").json().get("installations"):
        print(" 2) 콘텐츠 팩: 이미 설치됨")
    else:
        r = g.post(f"{GRAYLOG}/system/content_packs/{pid}/{rev}/installations",
                   json={"parameters": {}, "comment": "setup_monitoring.py"})
        r.raise_for_status()
        print(f" 2) 콘텐츠 팩: 설치함 (항목 {len(r.json().get('entities', []))}개)")

    # 3) URL 허용 목록
    wl = g.get(f"{GRAYLOG}/system/urlwhitelist").json()
    if any(e.get("value") == WHITELIST for e in wl.get("entries", [])):
        print(" 3) URL 허용 목록: 이미 있음")
    else:
        wl.setdefault("entries", []).append({"id": str(uuid.uuid4()), "type": "regex",
                                             "title": "local n8n webhooks", "value": WHITELIST})
        g.put(f"{GRAYLOG}/system/urlwhitelist", json=wl).raise_for_status()
        print(f" 3) URL 허용 목록: {WHITELIST} 추가")

    # 4) ED-A1
    from graylog_add_account_bruteforce import ensure_account_bruteforce
    print(" 4) ", end="")
    ensure_account_bruteforce(g, GRAYLOG)


def setup_n8n():
    print("[n8n]")
    wait("n8n", lambda: requests.get(f"{N8N}/healthz", timeout=5).status_code == 200)
    s = requests.Session()
    settings = s.get(f"{N8N}/rest/settings").json().get("data", {})
    needs_owner = settings.get("userManagement", {}).get("showSetupOnFirstLoad")

    # 5) 소유자 계정
    if needs_owner:
        email, pw = "owner@test.local", "Aa1" + secrets.token_urlsafe(15)
        r = s.post(f"{N8N}/rest/owner/setup", json={"email": email, "firstName": "Local",
                                                     "lastName": "Owner", "password": pw})
        r.raise_for_status()
        OWNER_FILE.parent.mkdir(exist_ok=True)
        OWNER_FILE.write_text(f"{email} {pw}\n", encoding="utf-8")
        print(f" 5) 소유자 계정: 만듦 ({email}, 비밀번호는 .secrets/n8n-owner.txt)")
    else:
        if not OWNER_FILE.exists():
            sys.exit(" 5) n8n 소유자가 이미 있는데 .secrets/n8n-owner.txt 가 없습니다. "
                     "'이메일 비밀번호' 한 줄로 적어 두고 다시 실행하세요.")
        print(" 5) 소유자 계정: 이미 있음")
    email, pw = OWNER_FILE.read_text(encoding="utf-8").split()[:2]
    s.post(f"{N8N}/rest/login", json={"emailOrLdapLoginId": email, "password": pw}).raise_for_status()

    # 6) 워크플로 가져오기 (같은 이름이 있으면 파일 내용으로 맞춤)
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    wf = wf[0] if isinstance(wf, list) else wf
    body = {k: wf[k] for k in ("name", "nodes", "connections") if k in wf}
    body["settings"] = wf.get("settings") or {}
    found = [w for w in s.get(f"{N8N}/rest/workflows").json()["data"] if w["name"] == wf["name"]]
    if found:
        wid = found[0]["id"]
        cur = s.get(f"{N8N}/rest/workflows/{wid}").json()["data"]
        s.patch(f"{N8N}/rest/workflows/{wid}", json={**body, "versionId": cur["versionId"]}).raise_for_status()
        print(f" 6) 워크플로: 이미 있음 → 파일 내용으로 갱신 (id {wid})")
    else:
        r = s.post(f"{N8N}/rest/workflows", json=body)
        r.raise_for_status()
        wid = r.json()["data"]["id"]
        print(f" 6) 워크플로: 가져옴 (id {wid})")

    # 7) 활성화
    cur = s.get(f"{N8N}/rest/workflows/{wid}").json()["data"]
    r = s.post(f"{N8N}/rest/workflows/{wid}/activate", json={"versionId": cur["versionId"]})
    if r.status_code >= 300:
        sys.exit(f" 7) 활성화 실패 {r.status_code}: {r.text[:300]}")
    cur = s.get(f"{N8N}/rest/workflows/{wid}").json()["data"]
    print(f" 7) 활성화: {'됨' if cur.get('active') else '안 됨'}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    setup_graylog()
    setup_n8n()
    print("\n완료. 확인: python scripts/scenario_ex05_sqli.py")


if __name__ == "__main__":
    main()
