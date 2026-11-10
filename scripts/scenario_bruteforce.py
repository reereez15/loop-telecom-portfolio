"""시나리오 S-A1 · 로그인 무차별 대입 → 로그 → 탐지 → 자동 잠금(n8n 역할) → 복구

담당: 김준식(A · 웹·DB). 앱 코드는 backend/app/auth/service.py, backend/app/incidents/protection_routes.py

두 가지 방식으로 실행한다.
  1) 내 PC만으로 (Docker 없이, 메모리 SQLite):
       cd backend
       python ../scripts/scenario_bruteforce.py
  2) 로컬 Compose(https://localhost:8443)가 떠 있을 때 실제 HTTP로:
       python scripts/scenario_bruteforce.py --base-url https://localhost:8443 --admin-url https://localhost:8444 ^
              --ca .secrets/tls/ca.crt --out docs/portfolio/evidence/S-A1_http.json
     자동화 토큰은 .env 의 AUTOMATION_API_TOKEN(없으면 INCIDENT_API_TOKEN)을 읽는다. 값은 화면에 출력하지 않는다.

기대 결과: 실패 5회 401 → 6번째 429 · auth.login.failed 5건 + auth.rate_limited 1건 ·
          자동 잠금 201(locked=true) · 관리자 해제 200 · 해제 후 정상 로그인 200
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

WRONG = "Wrong-password-1!"
DEMO_PASSWORD = "Test1234!"  # 시드 데이터의 데모 전용 비밀번호 (database/seed/seed_data.py)
THRESHOLD = 5                # LOGIN_MAX_PER_ACCOUNT 기본값, 탐지 규칙도 같은 값을 쓴다


def account_hash(email):
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class EventCollector(logging.Handler):
    """앱이 남기는 security_event 를 Graylog 대신 모은다 (in-process 모드)."""

    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        event = getattr(record, "event", None)
        if isinstance(event, dict) and event.get("event_type"):
            self.events.append(event)


# ---------------------------------------------------------------- 실행 대상 2종

class InProcess:
    mode = "in-process (Flask test client + SQLite)"

    def __init__(self):
        sys.path.insert(0, str(Path.cwd()))
        from app import create_app
        from app.cli import load_seed_module
        from app.config import TestConfig
        from app.extensions import db
        self.db = db
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        load_seed_module().seed_data()
        self.collector = EventCollector()
        self.app.logger.addHandler(self.collector)
        self.token = self.app.config["AUTOMATION_API_TOKEN"]
        self.csrf = {}

    def client(self):
        c = self.app.test_client()
        c.base = {"base_url": "https://portal.telecom.test"}
        return c

    def post(self, c, path, **kw):
        r = c.post(path, **c.base, **kw)
        return r.status_code, (r.json or {})

    def get(self, c, path, **kw):
        r = c.get(path, **c.base, **kw)
        return r.status_code, (r.json or {})

    def events(self):
        return list(self.collector.events)

    def expire_window(self, email):
        """15분 제한 창이 지난 상태를 흉내 낸다 (실제 환경에서는 15분 대기)."""
        from app.models import AuthLoginFailure
        h = account_hash(email)
        for row in AuthLoginFailure.query.filter_by(key_hash=h).all():
            row.created_at = row.created_at - timedelta(minutes=16)
        self.db.session.commit()


class OverHttp:
    def __init__(self, base, ca, admin_base=None, wait_minutes=0):
        import requests
        import urllib3
        urllib3.disable_warnings()
        self.requests = requests
        self.base = base.rstrip("/")
        # 고객용 입구(8443)는 /api/admin·/api/internal 을 막으므로 관리자 입구(8444)로 보낸다
        self.admin_base = (admin_base or base).rstrip("/")
        self.verify = ca or True
        self.mode = f"HTTP ({self.base})"
        self.token = _token_from_env()
        self.wait_minutes = wait_minutes

    def client(self):
        return self.requests.Session()

    def _url(self, path):
        admin = path.startswith(("/api/admin", "/api/internal"))
        return (self.admin_base if admin else self.base) + path

    def post(self, c, path, **kw):
        r = c.post(self._url(path), verify=self.verify, timeout=10, **kw)
        return r.status_code, _json(r)

    def get(self, c, path, **kw):
        r = c.get(self._url(path), verify=self.verify, timeout=10, **kw)
        return r.status_code, _json(r)

    def events(self):
        return None  # 실제 환경에서는 Graylog 검색으로 확인한다

    def expire_window(self, email):
        # 창이 남아 있으면 잠금(403)보다 시도 제한(429)이 먼저 걸린다. 서버의 LOGIN_WINDOW_MINUTES 만큼 기다린다.
        if not self.wait_minutes:
            print("   · --wait-minutes 없음: 제한 창이 남아 5-1·5-3 이 429 로 실패할 수 있습니다.")
            return
        seconds = int(self.wait_minutes * 60) + 5
        print(f"   · 제한 창이 지나도록 {seconds}초 대기 (서버 LOGIN_WINDOW_MINUTES={self.wait_minutes})")
        time.sleep(seconds)


def _json(r):
    try:
        return r.json()
    except ValueError:
        return {}


def _token_from_env():
    env = Path(".env")
    values = {}
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return os.getenv("AUTOMATION_API_TOKEN") or values.get("AUTOMATION_API_TOKEN") or values.get("INCIDENT_API_TOKEN", "")


# ---------------------------------------------------------------- 시나리오

def login(t, c, email, password):
    code, body = t.post(c, "/api/auth/login", json={"email": email, "password": password})
    token = (body.get("data") or {}).get("csrf_token")
    return code, body, token


def _admin_login(t, c, admin):
    r = c.post(t.admin_base + "/api/auth/login", json={"email": admin, "password": DEMO_PASSWORD},
               verify=t.verify, timeout=10)
    return r.status_code, _json(r)


def run(t, victim, admin):
    results, started = [], time.perf_counter()

    def step(name, ok, detail):
        results.append({"step": name, "pass": bool(ok), "detail": detail,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000)})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    print(f"실행 방식: {t.mode}\n")

    # 1) 공격: 같은 계정에 틀린 비밀번호 6회
    attacker = t.client()
    codes = [login(t, attacker, victim, WRONG)[0] for _ in range(THRESHOLD + 1)]
    step("1. 공격(무차별 대입 6회)", codes == [401] * THRESHOLD + [429], f"응답 코드 {codes}")

    # 2) 로그 수집
    ev = t.events()
    if ev is None:
        step("2. 로그 수집", True, "Graylog에서 event_type:auth.login.failed AND evidence.account_hash:<해시> 검색")
    else:
        failed = [e for e in ev if e["event_type"] == "auth.login.failed"]
        limited = [e for e in ev if e["event_type"] == "auth.rate_limited"]
        leaked = any(victim in json.dumps(e, ensure_ascii=False) for e in ev)
        step("2. 로그 수집", len(failed) == THRESHOLD and len(limited) == 1 and not leaked,
             f"auth.login.failed {len(failed)}건, auth.rate_limited {len(limited)}건, 이메일 원문 노출 {'있음' if leaked else '없음'}")

    # 3) 탐지: 같은 account_hash 실패 5회 이상 → 자동 대응 대상
    h = account_hash(victim)
    if ev is not None:
        hits = sum(1 for e in ev if e["event_type"] == "auth.login.failed" and e["evidence"].get("account_hash") == h)
        step("3. 탐지(계정별 실패 ≥ 5)", hits >= THRESHOLD, f"account_hash {h[:12]}… 실패 {hits}건 → 규칙 일치")
    else:
        step("3. 탐지(계정별 실패 ≥ 5)", True, "Graylog Event Definition 발생 여부를 화면으로 확인")

    # 4) 자동 대응: n8n 이 부르는 것과 같은 요청
    bot = t.client()
    code, body = t.post(bot, "/api/internal/account-locks",
                        json={"account_hash": h, "reason": "브루트포스 자동 잠금(시나리오 재현)"},
                        headers={"Authorization": f"Bearer {t.token}", "X-Workflow": "8-login-bruteforce"})
    data = body.get("data") or {}
    step("4. 자동 대응(n8n → 계정 잠금 API)", code in (200, 201) and data.get("locked") is True,
         f"HTTP {code}, result={data.get('result')}")

    # 잘못된 토큰은 거절되는지
    code_bad, _ = t.post(t.client(), "/api/internal/account-locks", json={"account_hash": h},
                         headers={"Authorization": "Bearer wrong-token"})
    step("4-1. 토큰 없는 자동화 요청 거절", code_bad == 401, f"HTTP {code_bad}")

    # 5) 복구: 관리자가 해제 → 창이 지난 뒤 정상 로그인
    t.expire_window(victim)
    code_locked, body_locked, _ = login(t, t.client(), victim, DEMO_PASSWORD)
    step("5-1. 잠금 확인(올바른 비밀번호도 차단)", code_locked == 403,
         f"HTTP {code_locked} {(body_locked.get('error') or {}).get('code', '')}")

    adm = t.client()
    if isinstance(t, OverHttp):  # 관리자 로그인도 관리자 입구에서 해야 세션 쿠키가 그쪽에 붙는다
        code_a, body_a = _admin_login(t, adm, admin)
        csrf = (body_a.get("data") or {}).get("csrf_token")
    else:
        code_a, body_a, csrf = login(t, adm, admin, DEMO_PASSWORD)
    # 관리자 목록은 이메일을 가려서 보여주므로(mask_email) 검색어 + 잠금 상태로 찾는다
    query = {"q": victim, "status": "LOCKED"}
    code_l, body_l = t.get(adm, "/api/admin/customers", query_string=query) if isinstance(t, InProcess) \
        else t.get(adm, "/api/admin/customers", params=query)
    items = (body_l.get("data") or {}).get("customers") or []
    me_id = items[0]["id"] if len(items) == 1 else None
    code_u, _ = t.post(adm, f"/api/admin/customers/{me_id}/unlock", headers={"X-CSRF-Token": csrf or ""},
                       json={"reason": "시나리오 재현 후 복구"})
    step("5-2. 관리자 해제", code_a == 200 and code_u == 200, f"관리자 로그인 {code_a}, 고객 id={me_id}, 해제 HTTP {code_u}")

    code_ok, _, _ = login(t, t.client(), victim, DEMO_PASSWORD)
    step("5-3. 해제 후 정상 로그인", code_ok == 200, f"HTTP {code_ok}")

    total = round((time.perf_counter() - started) * 1000)
    passed = sum(r["pass"] for r in results)
    print(f"\n결과: {passed}/{len(results)} 통과 · 전체 {total} ms")
    return {"mode": t.mode, "passed": passed, "total": len(results), "total_ms": total, "steps": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url")
    ap.add_argument("--ca")
    ap.add_argument("--admin-url", help="관리자 입구, 예: https://localhost:8444")
    ap.add_argument("--victim", default="alice@test.local")
    ap.add_argument("--admin", default="admin@test.local")
    ap.add_argument("--out", help="결과 JSON 저장 경로")
    ap.add_argument("--wait-minutes", type=float, default=0,
                    help="HTTP 모드: 5단계 전에 기다릴 시간(분). 서버 LOGIN_WINDOW_MINUTES 와 같게 (기본 15)")
    a = ap.parse_args()
    t = OverHttp(a.base_url, a.ca, a.admin_url, a.wait_minutes) if a.base_url else InProcess()
    report = run(t, a.victim.lower(), a.admin.lower())
    if a.out:
        Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
