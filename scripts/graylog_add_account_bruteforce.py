"""Graylog 에 'ED-A1 | 계정 브루트포스(앱 로그)' 탐지 규칙과 n8n 알림을 만든다. — 김준식

왜 따로 있나
  팀 콘텐츠 팩의 ED-08 은 모의 로그 형식(rule:login-bruteforce AND username:*)을 찾는다.
  실제 앱(Flask)은 이메일을 남기지 않고 event_type:auth.login.failed + account_hash(SHA-256) 로 남기므로
  ED-08 은 앱 로그에 걸리지 않는다. 이 스크립트는 앱 로그 형식에 맞는 규칙을 더한다(이미 있으면 갱신).

실행 (콘텐츠 팩 설치 뒤)
  python scripts/graylog_add_account_bruteforce.py --password-file .secrets/graylog-admin.txt
  옵션: --url http://localhost:9000  --user admin  --threshold 5  --window-minutes 15
        --webhook http://n8n:5678/webhook/login-bruteforce
"""
import argparse
import getpass
import sys
from pathlib import Path

import requests

TITLE = "ED-A1 | 계정 브루트포스(앱 로그)"
NOTIF_TITLE = "N8N-A1 | 계정 브루트포스(앱 로그)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:9000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password-file")
    ap.add_argument("--threshold", type=int, default=5, help="앱 LOGIN_MAX_PER_ACCOUNT 와 같게")
    ap.add_argument("--window-minutes", type=int, default=15, help="앱 LOGIN_WINDOW_MINUTES 와 같게")
    ap.add_argument("--webhook", default="http://n8n:5678/webhook/login-bruteforce")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pw = Path(a.password_file).read_text(encoding="utf-8").strip() if a.password_file else getpass.getpass("Graylog 비밀번호: ")
    g = requests.Session()
    g.auth = (a.user, pw)
    g.headers.update({"X-Requested-By": "cli", "Accept": "application/json"})
    api = a.url.rstrip("/") + "/api"

    notification = {
        "title": NOTIF_TITLE,
        "description": "Graylog → n8n 8- 브루트포스 계정잠금. 계정은 이메일 대신 account_hash 로 넘긴다.",
        "config": {
            "type": "http-notification-v2",
            "url": a.webhook, "method": "POST", "content_type": "JSON", "time_zone": "Asia/Seoul",
            "basic_auth": None, "api_key_as_header": False, "api_key": "", "api_secret": None,
            "skip_tls_verification": False, "headers": "",
            "body_template": (
                '{\n  "event_definition": "${event_definition_title}",\n'
                '  "alerts": [\n    {\n      "account_hash": "${event.key}",\n'
                '      "count": "' + str(a.threshold) + '+",\n      "student": "security-team"\n    }\n  ]\n}'
            ),
        },
    }
    nots = g.get(f"{api}/events/notifications", params={"per_page": 200}).json()["notifications"]
    old = next((n for n in nots if n["title"] == NOTIF_TITLE), None)
    r = g.put(f"{api}/events/notifications/{old['id']}", json=notification) if old else \
        g.post(f"{api}/events/notifications", json=notification)
    r.raise_for_status()
    notif_id = r.json()["id"]
    print(f"알림 {'갱신' if old else '생성'}: {NOTIF_TITLE} → {a.webhook}")

    definition = {
        "title": TITLE,
        "description": f"같은 account_hash 로그인 실패 {a.threshold}회 이상 / {a.window_minutes}분. "
                       "앱 auth.login.failed 이벤트 기준(이메일 원문 없음).",
        "priority": 2, "alert": True,
        "config": {
            "type": "aggregation-v1",
            "query": "event_type:auth.login.failed AND _exists_:account_hash",
            "query_parameters": [], "filters": [], "streams": [], "stream_categories": [],
            "group_by": ["account_hash"],
            "series": [{"type": "count", "id": "count-", "field": None}],
            "conditions": {"expression": {"expr": ">=", "left": {"expr": "number-ref", "ref": "count-"},
                                          "right": {"expr": "number", "value": a.threshold}}},
            "search_within_ms": a.window_minutes * 60_000,
            "execute_every_ms": 60_000,
            "use_cron_scheduling": False, "event_limit": 100,
        },
        "field_spec": {"account_hash": {"data_type": "string", "providers": [
            {"type": "template-v1", "template": "${source.account_hash}", "require_values": False}]}},
        "key_spec": ["account_hash"],
        "notification_settings": {"grace_period_ms": a.window_minutes * 60_000, "backlog_size": 1},
        "notifications": [{"notification_id": notif_id, "notification_parameters": None}],
        "storage": [{"type": "persist-to-streams-v1", "streams": ["000000000000000000000002"]}],
    }
    eds = g.get(f"{api}/events/definitions", params={"per_page": 200}).json()["event_definitions"]
    old = next((d for d in eds if d["title"] == TITLE), None)
    if old:
        definition["id"] = old["id"]
        r = g.put(f"{api}/events/definitions/{old['id']}", json=definition, params={"schedule": "true"})
    else:
        r = g.post(f"{api}/events/definitions", json=definition, params={"schedule": "true"})
    if r.status_code >= 300:
        sys.exit(f"규칙 저장 실패 {r.status_code}: {r.text[:300]}")
    print(f"규칙 {'갱신' if old else '생성'}: {TITLE} (실패 ≥ {a.threshold} / {a.window_minutes}분, 1분마다 검사)")


if __name__ == "__main__":
    main()
