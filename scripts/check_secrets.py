"""제출 전 점검: 현재 파일과 (선택) 커밋 기록에 비밀값이 남아 있는지 찾는다.

    python scripts/check_secrets.py            # 현재 파일만
    python scripts/check_secrets.py --history  # 커밋 기록 전체까지
찾으면 파일 위치와 앞 6자만 보여 주고 종료 코드 1. 없으면 0.
테스트 고정값(Test1234!, test-incident-token 등)은 '데모 전용'이라 제외한다.
캡처 이미지는 이 스크립트로 못 본다 → docs/portfolio/evidence 의 캡처를 눈으로 한 번 더 확인할 것.
"""
import re
import subprocess
import sys
from pathlib import Path

RULES = {
    "Discord 웹훅": re.compile(r"discord(?:app)?\.com/api/webhooks/(?!12345/|REDACTED)\d+/[A-Za-z0-9_\-]{20,}"),
    "API 키 헤더 값": re.compile(r'"name"\s*:\s*"(?:X-API-Key|Authorization)"\s*,[\s+\-]*"value"\s*:\s*"(?!=|\{\{|REDACTED)(?:Bearer\s+)?([^"]{16,})"', re.I),
    "Bearer 토큰": re.compile(r"Bearer\s+(?!\$|\{|<)([A-Za-z0-9_\-\.]{24,})"),
    "카카오페이 실키": re.compile(r"(?:DEV|PRD)[A-Z0-9]{20,}"),
    "개인키": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ".env 값": re.compile(r"^(?:[A-Z_]*(?:PASSWORD|TOKEN|SECRET|KEY))=(?!$|REPLACE|<|change|local-|test-|fixture)[^\s#]{8,}", re.M),
}
SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "venv", "__pycache__", ".secrets"}
SKIP_FILES = {"package-lock.json", "check_secrets.py", "sanitize_repo.py"}


def scan_text(label, text, hits):
    for name, rx in RULES.items():
        for m in rx.finditer(text):
            value = m.group(m.lastindex or 0)
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{label}:{line}  {name}  {value[:6]}…")


def main():
    hits = []
    for f in Path(".").rglob("*"):
        if f.is_dir() or any(p in SKIP_DIRS for p in f.parts) or f.name in SKIP_FILES:
            continue
        if f.name == ".env" or f.suffix.lower() in {".png", ".jpg", ".webp", ".gif", ".ico", ".pdf", ".zip"}:
            if f.name == ".env":
                tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(f)], capture_output=True).returncode == 0
                if tracked:
                    hits.append(f"{f}  .env 파일이 git 에 올라가 있음")
            continue
        try:
            scan_text(str(f), f.read_text(encoding="utf-8"), hits)
        except (UnicodeDecodeError, OSError):
            continue
    if "--history" in sys.argv:
        log = subprocess.run(["git", "log", "--all", "-p", "--no-color", "--text"], capture_output=True).stdout
        scan_text("history", log.decode("utf-8", "replace"), hits)
    for h in hits:
        print("발견:", h)
    print(f"\n점검 결과: {'문제 ' + str(len(hits)) + '건' if hits else '비밀값 없음'}")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
