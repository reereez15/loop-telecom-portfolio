"""S-A1 전 구간 재현: 공격 → 앱 로그 → Graylog ED-A1 탐지 → n8n 자동 잠금 → 관리자 해제·복구. — 김준식

scenario_bruteforce.py 는 4단계(자동 대응)를 n8n 과 같은 요청으로 '직접' 보낸다.
이 스크립트는 4단계를 직접 보내지 않고, Graylog 가 탐지해 n8n 이 잠그는지를 기다려서 잰다.

실행 (1·2단계 설치 + graylog_add_account_bruteforce.py 실행 뒤)
  python scripts/scenario_bruteforce_e2e.py --register --victim s-a1-01@test.local \
      --graylog-password-file .secrets/graylog-admin.txt --out docs/portfolio/evidence/S-A1_e2e.json
  ※ 같은 계정은 Graylog 알림 유예(15분) 동안 다시 알리지 않는다. 반복할 땐 --victim 이름을 바꾼다.
  ※ 앱 LOGIN_WINDOW_MINUTES 가 지나야 5-3(정상 로그인)이 200 이 된다. --wait-minutes 로 맞춘다.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3

WRONG, DEMO_PASSWORD, THRESHOLD = "Wrong-Password-1!", "Test1234!", 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://localhost:8443")
    ap.add_argument("--admin-url", default="https://localhost:8444")
    ap.add_argument("--ca", default=".secrets/tls/ca.crt")
    ap.add_argument("--graylog", default="http://localhost:9000")
    ap.add_argument("--graylog-password-file", required=True)
    ap.add_argument("--victim", default="bob@test.local")
    ap.add_argument("--admin", default="admin@test.local")
    ap.add_argument("--timeout", type=int, default=240, help="자동 잠금을 기다릴 최대 초")
    ap.add_argument("--wait-minutes", type=float, default=0, help="해제 후 로그인 전 대기(앱 LOGIN_WINDOW_MINUTES)")
    ap.add_argument("--register", action="store_true", help="시험 계정을 먼저 가입시킨다(비밀번호 Test1234!)")
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    urllib3.disable_warnings()
    victim = a.victim.lower()
    h = hashlib.sha256(victim.encode()).hexdigest()

    g = requests.Session()
    g.auth = ("admin", Path(a.graylog_password_file).read_text(encoding="utf-8").strip())
    g.headers.update({"X-Requested-By": "cli", "Accept": "application/json"})
    gapi = a.graylog.rstrip("/") + "/api"

    results, t0 = [], time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def step(name, ok, detail):
        results.append({"step": name, "pass": bool(ok), "detail": detail, "elapsed_s": round(time.perf_counter() - t0, 1)})
        print(f"[{'PASS' if ok else 'FAIL'}] {results[-1]['elapsed_s']:>6}s  {name} — {detail}")

    def post(base, s, path, **kw):
        return s.post(base + path, verify=a.ca, timeout=10, **kw)

    adm = requests.Session()
    r = post(a.admin_url, adm, "/api/auth/login", json={"email": a.admin, "password": DEMO_PASSWORD})
    csrf = (r.json().get("data") or {}).get("csrf_token")

    def victim_row():
        r = adm.get(a.admin_url + "/api/admin/customers", params={"q": victim}, verify=a.ca, timeout=10)
        rows = (r.json().get("data") or {}).get("customers") or []
        return rows[0] if len(rows) == 1 else None

    if a.register:  # 같은 계정은 Graylog 알림 유예(15분) 동안 다시 알리지 않으므로, 반복 시험엔 새 계정을 쓴다
        r = post(a.base_url, requests.Session(), "/api/auth/register",
                 json={"email": victim, "password": DEMO_PASSWORD, "name": "시나리오시험"})
        print(f"시험 계정 가입: HTTP {r.status_code}")
    row = victim_row()
    if row is None:
        sys.exit(f"{victim} 고객 계정을 찾지 못했습니다. --register 로 새로 만들 수 있습니다.")
    if row.get("status") == "LOCKED":
        sys.exit(f"{victim} 가 이미 잠겨 있습니다. 관리자 콘솔에서 해제하고 다시 실행하세요.")

    # 1) 공격
    s = requests.Session()
    codes = [post(a.base_url, s, "/api/auth/login", json={"email": victim, "password": WRONG}).status_code
             for _ in range(THRESHOLD + 1)]
    step("1. 공격(틀린 비밀번호 6회)", codes == [401] * THRESHOLD + [429], f"응답 {codes}")
    attack_end = time.perf_counter()

    # 2) 로그 수집 (Graylog 검색)
    found = 0
    for _ in range(30):
        q = f"event_type:auth.login.failed AND account_hash:{h}"
        found = g.get(f"{gapi}/search/universal/relative", params={"query": q, "range": 300, "limit": 1}).json().get("total_results", 0)
        if found >= THRESHOLD:
            break
        time.sleep(2)
    leaked = g.get(f"{gapi}/search/universal/relative", params={"query": f'"{victim}"', "range": 300, "limit": 1}).json().get("total_results", 0)
    step("2. 로그 수집(Graylog)", found >= THRESHOLD and leaked == 0,
         f"auth.login.failed {found}건 (account_hash {h[:12]}…), 이메일 원문 검색 {leaked}건")

    # 3) 탐지 (ED-A1 이벤트) + 4) 자동 대응 (n8n → 계정 잠금) — 기다리며 잰다
    detected = locked = lock_reason = None
    deadline = time.perf_counter() + a.timeout
    while time.perf_counter() < deadline and not (detected and locked):
        if not detected:
            ev = g.post(f"{gapi}/events/search", json={"query": f"key:{h}", "page": 1, "per_page": 5,
                                                       "timerange": {"type": "relative", "range": 600}}).json()
            hits = [e for e in ev.get("events", []) if "ED-A1" in (e["event"].get("message") or "")]
            if hits:
                detected = (round(time.perf_counter() - t0, 1), hits[0]["event"]["timestamp"])
        if not locked:
            row = victim_row()
            if row and row.get("status") == "LOCKED":
                locked = round(time.perf_counter() - t0, 1)
                lock_reason = row.get("lock_reason")
        time.sleep(3)
    step("3. 탐지(Graylog ED-A1)", bool(detected),
         f"이벤트 발생 {detected[0]}s 시점 (Graylog {detected[1]})" if detected else f"{a.timeout}s 안에 이벤트 없음")
    step("4. 자동 대응(n8n → 계정 잠금)", bool(locked),
         f"관리자 목록 상태 LOCKED({lock_reason}), 공격 시작 후 {locked}s" if locked else f"{a.timeout}s 안에 잠기지 않음")

    # 5) 잠금 확인 → 관리자 해제 → 정상 로그인
    # 제한 창이 남아 있으면 잠금(403)보다 시도 제한(429)이 먼저 걸린다 → 공격이 끝난 뒤 창만큼은 지나게 한다
    remain = attack_end + a.wait_minutes * 60 + 5 - time.perf_counter()
    if a.wait_minutes and remain > 0:
        print(f"   · 제한 창이 지나도록 {round(remain)}초 더 대기")
        time.sleep(remain)
    c = post(a.base_url, requests.Session(), "/api/auth/login", json={"email": victim, "password": DEMO_PASSWORD})
    step("5-1. 잠금 확인(올바른 비밀번호도 차단)", c.status_code == 403, f"HTTP {c.status_code} {(c.json().get('error') or {}).get('code', '')}")
    row = victim_row()
    u = post(a.admin_url, adm, f"/api/admin/customers/{row['id']}/unlock", headers={"X-CSRF-Token": csrf or ""},
             json={"reason": "S-A1 전 구간 재현 후 복구"})
    step("5-2. 관리자 해제", u.status_code == 200, f"HTTP {u.status_code}")
    ok = post(a.base_url, requests.Session(), "/api/auth/login", json={"email": victim, "password": DEMO_PASSWORD})
    step("5-3. 해제 후 정상 로그인", ok.status_code == 200, f"HTTP {ok.status_code}")

    passed = sum(x["pass"] for x in results)
    print(f"\n결과: {passed}/{len(results)} 통과 · 탐지까지 {detected[0] if detected else '-'}s · 자동 잠금까지 {locked or '-'}s")
    if a.out:
        Path(a.out).write_text(json.dumps({"scenario": "S-A1 전 구간(Graylog·n8n 경유)", "started_at": started_at,
                                           "victim_account_hash": h[:12] + "…", "passed": passed, "total": len(results),
                                           "detect_s": detected[0] if detected else None, "auto_lock_s": locked,
                                           "steps": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
