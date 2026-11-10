"""팀 저장소를 개인 저장소로 옮기면서 커밋 기록 속 민감정보(웹훅·API 키)를 지운다.

사용법 (PowerShell 또는 bash, 저장소 바깥의 빈 폴더에서):
    pip install git-filter-repo
    python sanitize_repo.py https://github.com/telecom-carrier-Loop/telecom-security-project.git loop-clean

동작:
  1) 원본을 --mirror 로 복제한다 (원본 저장소는 건드리지 않는다)
  2) 모든 커밋의 모든 파일에서 아래 값을 찾아 목록을 만든다
       - Discord 웹훅 주소
       - JSON 안 "name": "X-API-Key" / "Authorization" 헤더의 "value" (n8n 워크플로)
       - Bearer 토큰 문자열
  3) 찾은 값을 REDACTED 로 바꾸는 규칙 파일을 '저장소 바깥' 임시 폴더에 만들고 git filter-repo 로 기록 전체를 다시 쓴다
  4) 다시 쓴 기록 전체를 재검사해서 남은 값이 0개인지 확인한다
찾은 값은 화면에 앞 6자만 보여 준다. 규칙 파일은 작업이 끝나면 지운다.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

WEBHOOK = re.compile(rb"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]+")
# 패치 출력은 줄마다 +/- 가 붙으므로 줄 사이 공백에 [+\- ] 를 허용한다
HEADER_VALUE = re.compile(rb'"name"\s*:\s*"(?:X-API-Key|Authorization)"\s*,[\s+\-]*"value"\s*:\s*"(?:Bearer\s+)?([^"\s{=][^"]{15,})"', re.I)
BEARER = re.compile(rb"Bearer\s+([A-Za-z0-9_\-\.]{24,})")
SAFE = {b"test-incident-token", b"local-incident-token"}  # 테스트 고정값 (비밀 아님)
FIXTURE = re.compile(rb"/webhooks/12345/")  # 테스트용 가짜 웹훅


def git(*args, cwd=None, binary=False):
    out = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def find_secrets(repo: Path) -> set:
    history = git("log", "--all", "-p", "--no-color", "--text", cwd=repo, binary=True)
    found = set()
    for m in WEBHOOK.finditer(history):
        if not FIXTURE.search(m.group(0)):
            found.add(m.group(0))
    for rx in (HEADER_VALUE, BEARER):
        for m in rx.finditer(history):
            value = m.group(1)
            if value not in SAFE and not value.startswith(b"{{") and b"$" not in value:
                found.add(value)
    return found


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    source, target = sys.argv[1], Path(sys.argv[2]).resolve()
    if target.exists():
        sys.exit(f"{target} 가 이미 있습니다. 빈 경로를 지정하세요.")
    print("1) 원본 미러 복제 …")
    git("clone", "--mirror", "--quiet", source, str(target))

    print("2) 기록 전체에서 민감정보 찾기 …")
    secrets = find_secrets(target)
    for s in sorted(secrets):
        kind = "웹훅" if s.startswith(b"https://") else "API 키/토큰"
        shown = s.split(b"/")[-1][:6] if kind == "웹훅" else s[:6]
        print(f"   - {kind}: {shown.decode()}…")
    if not secrets:
        print("   찾은 값 없음. 그대로 사용해도 됩니다.")
        return

    print("3) 기록 다시 쓰기 (git filter-repo) …")
    with tempfile.TemporaryDirectory() as tmp:
        rules = Path(tmp) / "replace.txt"
        lines = []
        for s in sorted(secrets, key=len, reverse=True):
            repl = b"https://discord.com/api/webhooks/REDACTED" if s.startswith(b"https://") else b"REDACTED_SET_IN_N8N_CREDENTIAL"
            lines.append(s + b"==>" + repl)
        rules.write_bytes(b"\n".join(lines) + b"\n")
        subprocess.run(["git", "filter-repo", "--force", "--replace-text", str(rules)], cwd=target, check=True)

    print("4) 재검사 …")
    history = git("log", "--all", "-p", "--no-color", "--text", cwd=target, binary=True)
    left = [s for s in secrets if s in history]
    if left:
        sys.exit(f"   남은 값 {len(left)}개 — 푸시하지 마세요.")
    print(f"   남은 값 0개 (지운 값 {len(secrets)}개). 커밋 수: {git('rev-list', '--all', '--count', cwd=target).strip()}")
    print("\n다음 단계 (GitHub에서 빈 저장소를 먼저 만든 뒤):")
    print(f"   cd {target}")
    print("   git push --mirror https://github.com/<내아이디>/<저장소이름>.git")
    print("\n※ 이미 공개된 값은 기록을 지워도 남아 있을 수 있습니다. 팀에 웹훅 재발급과 자동화 토큰 교체를 요청하세요.")


if __name__ == "__main__":
    main()
