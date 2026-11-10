"""새 PC 준비 2단계 — .env 의 관제(Graylog) 칸을 채운다. — 김준식

  python infrastructure/tools/prepare-local.py   # 1) 팀 스크립트: .env·TLS 인증서 생성
  python scripts/setup_portfolio_env.py          # 2) 이 스크립트: Graylog 비밀번호 등 나머지 칸
  python scripts/setup_portfolio_env.py --demo   #    시연용: 로그인 제한 창 1분 (시나리오가 빨리 끝남)

하는 일 (이미 값이 있으면 건드리지 않는다)
  - GRAYLOG_PASSWORD_SECRET  : 무작위 64자
  - GRAYLOG_ROOT_PASSWORD_SHA2 : 무작위 관리자 비밀번호의 SHA-256 → 비밀번호 원문은 .secrets/graylog-admin.txt
  - GRAYLOG_GELF_HOST=graylog : 앱 로그를 관제 스택으로 보냄
  - --demo 일 때 LOGIN_WINDOW_MINUTES=1
.env 와 .secrets/ 는 git 에 올라가지 않는다.
"""
import argparse
import hashlib
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def set_if_empty(lines, key, value):
    """KEY= 가 비어 있으면 채우고, 줄이 없으면 붙인다. 이미 값이 있으면 False."""
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key and not line.lstrip().startswith("#"):
            if line.split("=", 1)[1].strip():
                return False
            lines[i] = f"{key}={value}"
            return True
    lines.append(f"{key}={value}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="LOGIN_WINDOW_MINUTES=1 (시연용)")
    ap.add_argument("--env", default=str(ROOT / ".env"))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    env = Path(a.env)
    if not env.exists():
        sys.exit(".env 가 없습니다. 먼저 python infrastructure/tools/prepare-local.py 를 실행하세요.")
    secrets_dir = env.parent / ".secrets"
    secrets_dir.mkdir(exist_ok=True)
    pw_file = secrets_dir / "graylog-admin.txt"
    lines = env.read_text(encoding="utf-8").splitlines()
    done = []

    if set_if_empty(lines, "GRAYLOG_PASSWORD_SECRET", secrets.token_hex(32)):
        done.append("GRAYLOG_PASSWORD_SECRET")
    has_sha = any(l.startswith("GRAYLOG_ROOT_PASSWORD_SHA2=") and l.split("=", 1)[1].strip() for l in lines)
    if not has_sha:
        if pw_file.exists():
            pw = pw_file.read_text(encoding="utf-8").strip()
        else:
            pw = secrets.token_urlsafe(18)
            pw_file.write_text(pw + "\n", encoding="utf-8")
        set_if_empty(lines, "GRAYLOG_ROOT_PASSWORD_SHA2", hashlib.sha256(pw.encode()).hexdigest())
        done.append("GRAYLOG_ROOT_PASSWORD_SHA2 (비밀번호: .secrets/graylog-admin.txt)")
    elif not pw_file.exists():
        print("주의: GRAYLOG_ROOT_PASSWORD_SHA2 는 이미 있지만 .secrets/graylog-admin.txt 가 없습니다. "
              "직접 정한 Graylog 비밀번호를 그 파일에 한 줄로 적어 주세요(시나리오 스크립트가 읽음).")
    if set_if_empty(lines, "GRAYLOG_GELF_HOST", "graylog"):
        done.append("GRAYLOG_GELF_HOST=graylog")
    if a.demo:
        for i, l in enumerate(lines):
            if l.startswith("LOGIN_WINDOW_MINUTES="):
                lines[i] = "LOGIN_WINDOW_MINUTES=1"
                break
        else:
            lines.append("LOGIN_WINDOW_MINUTES=1")
        done.append("LOGIN_WINDOW_MINUTES=1 (시연용)")

    env.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("채운 값:", ", ".join(done) if done else "없음 (이미 다 채워져 있음)")
    print("Graylog 로그인: admin / .secrets/graylog-admin.txt 의 비밀번호")


if __name__ == "__main__":
    main()
