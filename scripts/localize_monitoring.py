"""학원망용 Graylog 콘텐츠 팩·n8n 워크플로를 '내 PC 한 대' 주소로 바꾼 사본을 만든다.

    python scripts/localize_monitoring.py
결과: monitoring/local/graylog/*.json, monitoring/local/n8n/*.json (원본은 그대로 둔다)

바꾸는 것
  - n8n → 앱 API      http://host.docker.internal:5000  → http://api:5000      (같은 Docker 네트워크)
  - Graylog → n8n     http://host.docker.internal:5678  → http://n8n:5678
  - 지운 비밀값 자리   REDACTED…                         → {{ $env.AUTOMATION_API_TOKEN }} / {{ $env.DISCORD_WEBHOOK_URL }}
    (비밀값은 .env → n8n 컨테이너 환경변수로만 들어가고 JSON 에는 남지 않는다)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URLS = {
    "http://host.docker.internal:5000": "http://api:5000",
    "http://host.docker.internal:5678": "http://n8n:5678",
}
SECRETS = {
    "https://discord.com/api/webhooks/REDACTED": "{{ $env.DISCORD_WEBHOOK_URL }}",
    "REDACTED_SET_IN_N8N_CREDENTIAL": "{{ $env.AUTOMATION_API_TOKEN }}",
}


def fix(value, stats):
    if isinstance(value, dict):
        return {k: fix(v, stats) for k, v in value.items()}
    if isinstance(value, list):
        return [fix(v, stats) for v in value]
    if not isinstance(value, str):
        return value
    new = value
    for a, b in URLS.items():
        if a in new:
            new, stats["url"] = new.replace(a, b), stats["url"] + new.count(a)
    for a, b in SECRETS.items():
        if a in new:
            new, stats["secret"] = new.replace(a, b), stats["secret"] + new.count(a)
            if not new.startswith("="):
                new = "=" + new  # n8n 은 '=' 로 시작해야 표현식으로 읽는다
    return new


def main():
    # n8n/workflows/*.json = 팀 원본(김준오, 손대지 않음), n8n/workflows/portfolio/*.json = 로컬 재현용 수정본(김준식)
    for src_dir, dst in ((ROOT / "monitoring/graylog", "graylog"), (ROOT / "monitoring/n8n/workflows", "n8n"),
                         (ROOT / "monitoring/n8n/workflows/portfolio", "n8n/portfolio")):
        out = ROOT / "monitoring/local" / dst
        out.mkdir(parents=True, exist_ok=True)
        for f in sorted(src_dir.glob("*.json")):
            stats = {"url": 0, "secret": 0}
            data = fix(json.loads(f.read_text(encoding="utf-8-sig")), stats)
            (out / f.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{dst}/{f.name}: 주소 {stats['url']}곳, 비밀값 자리 {stats['secret']}곳")


if __name__ == "__main__":
    main()
