"""팀 시나리오 EX-05 SQL Injection 재현: 모의 공격 로그 → Graylog ED-EX-05 → n8n → 관리자 보안 인시던트. — 김준식

탐지 규칙·워크플로는 김준오(관제·자동화) 작업이고, 이 스크립트는 그것을 로컬에서 한 번에 재현·측정하는 용도다.
학원 시험 스크립트(monitoring/graylog/attack-test/PC2_to_PC1/)와 같은 GELF 형식이며 보낼 곳만 로컬이다.
같은 출발지 IP 는 Graylog 알림 유예(5분) 동안 다시 알리지 않으므로 매번 다른 문서용 IP(198.51.100.x)를 쓴다.

  python scripts/scenario_ex05_sqli.py --out docs/portfolio/evidence/EX-05_e2e.json
"""
import argparse
import json
import random
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gelf", default="127.0.0.1:12201")
    ap.add_argument("--admin-url", default="https://localhost:8444")
    ap.add_argument("--ca", default=".secrets/tls/ca.crt")
    ap.add_argument("--admin", default="admin@test.local")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    urllib3.disable_warnings()

    src_ip = f"198.51.100.{random.randint(2, 254)}"
    msg = {"version": "1.1", "host": "local-attack-sim", "short_message": "[SIMULATED] EX-05 SQL Injection",
           "_rule": "sqli-detected", "_src_ip": src_ip, "_test_case": "EX-05_SQLInjection",
           "_uri": "/api/auth/login?email=' OR 1=1 --", "_student": "security-team"}
    host, port = a.gelf.split(":")
    adm = requests.Session()
    r = adm.post(a.admin_url + "/api/auth/login", json={"email": a.admin, "password": "Test1234!"}, verify=a.ca, timeout=10)
    if r.status_code != 200:
        sys.exit(f"관리자 로그인 실패 HTTP {r.status_code}")

    def incidents():
        r = adm.get(a.admin_url + "/api/admin/incidents", verify=a.ca, timeout=10)
        return (r.json().get("data") or {}).get("incidents") or []

    before = {i["id"] for i in incidents()}
    t0 = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(json.dumps(msg).encode(), (host, int(port)))
    print(f"[{0:>5.1f}s] 1. 공격 로그 전송 (GELF UDP {a.gelf}, src_ip={src_ip})")

    found = None
    while time.perf_counter() - t0 < a.timeout:
        new = [i for i in incidents() if i["id"] not in before and "EX-05" in (i.get("title") or "")]
        mine = [i for i in new if src_ip in json.dumps(i.get("evidence") or {}, ensure_ascii=False)] or new
        if mine:
            found = mine[0]
            break
        time.sleep(3)
    elapsed = round(time.perf_counter() - t0, 1)
    ok = found is not None
    print(f"[{elapsed:>5.1f}s] 2~4. Graylog 탐지 → n8n → 인시던트 등록: "
          + (f"#{found['id']} '{found['title']}' {found['severity']} {found['status']}" if ok else f"{a.timeout}s 안에 없음"))
    if a.out:
        Path(a.out).write_text(json.dumps({
            "scenario": "EX-05 SQL Injection (팀 규칙·워크플로: 김준오)", "started_at": started_at, "src_ip": src_ip,
            "pass": ok, "incident_s": elapsed if ok else None,
            "incident": {k: found.get(k) for k in ("id", "title", "severity", "status", "source")} if ok else None,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
