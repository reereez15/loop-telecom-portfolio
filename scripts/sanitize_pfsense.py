"""pfSense config.xml 에서 비밀값을 지워 포트폴리오용 사본을 만든다.

    python scripts/sanitize_pfsense.py <원본 config.xml> security/pfsense/config.sanitized.xml

지우는 것 (값을 REDACTED 로 바꿈, 태그와 구조는 남김)
  - 계정 비밀번호 해시(bcrypt-hash, password, sha512-hash 등), SSH 공개키, IPsec PSK
  - 인증서 개인키(prv)·인증서 본문(crt)·CSR, OpenVPN TLS 정적 키(tls, shared_key)
  - SNMP 커뮤니티, RADIUS/LDAP 비밀, SMTP·DynDNS·API 키, Suricata oinkcode 등
  - 웹훅 주소(Discord·Slack·Telegram)
남기는 것: 인터페이스, 별칭, 방화벽·NAT 규칙, OpenVPN 서버 설정(키 제외), 사설 IP
끝나면 남은 의심 값(개인키 머리말, 긴 base64, bcrypt 형식)을 다시 찾아 0개인지 보여 준다.
원본 파일은 바꾸지 않는다.
"""
import re
import sys
from pathlib import Path

SECRET_TAGS = {
    # 계정·인증
    "bcrypt-hash", "sha512-hash", "md5-hash", "password", "passwordenc", "pass", "passwd",
    "authorizedkeys", "ipsecpsk", "pre-shared-key", "psk", "otp_seed", "apikey", "api_key",
    "ldap_bindpw", "radius_secret", "radius_secret2", "radius_secret3", "radius_secret4", "secret",
    # 인증서·키
    "prv", "crt", "csr", "tls", "shared_key", "key",
    # 모니터링·알림·외부 서비스
    "rocommunity", "rwcommunity", "trapstring", "username_password", "smtppassword", "pushoverapikey",
    "pushoveruserkey", "telegramapi", "slack_api_key", "oinkcode", "oinkmastercode", "etpro_code",
    "gplv2_oinkcode", "maxmind_key", "updatekey", "dyndns_password", "auth_pass", "auth_password",
}
WEBHOOK = re.compile(r"https://(?:(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services|api\.telegram\.org/bot)[^\s<\"']+")
LEFTOVER = {
    "개인키 머리말": re.compile(r"-----BEGIN [A-Z ]*(?:PRIVATE KEY|OpenVPN Static key)"),
    "bcrypt 해시": re.compile(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}"),
    "긴 base64(300자 이상)": re.compile(r"[A-Za-z0-9+/=]{300,}"),
    "웹훅 주소": WEBHOOK,
}


def sanitize(text: str):
    counts = {}

    def repl(m):
        tag = m.group(1)
        value = m.group(2)
        if not value.strip() or value.strip() in ("REDACTED", "<![CDATA[]]>"):
            return m.group(0)
        counts[tag] = counts.get(tag, 0) + 1
        return f"<{tag}>REDACTED</{tag}>"

    names = "|".join(sorted((re.escape(t) for t in SECRET_TAGS), key=len, reverse=True))
    text = re.sub(rf"<({names})>(.*?)</\1>", repl, text, flags=re.S)
    text, n = WEBHOOK.subn("https://REDACTED-WEBHOOK", text)
    if n:
        counts["webhook-url"] = n
    return text, counts


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if src.resolve() == dst.resolve():
        sys.exit("원본과 결과 경로가 같습니다. 다른 경로를 지정하세요.")
    text = src.read_text(encoding="utf-8")
    out, counts = sanitize(text)
    for tag, n in sorted(counts.items()):
        print(f"  지움: <{tag}> {n}건")
    left = {name: len(rx.findall(out)) for name, rx in LEFTOVER.items()}
    for name, n in left.items():
        print(f"  재검사: {name} {n}건")
    if any(left.values()):
        sys.exit("남은 의심 값이 있습니다. 결과 파일을 만들지 않았습니다.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding="utf-8", newline="\n")
    print(f"결과: {dst} (지운 값 {sum(counts.values())}개, 남은 의심 값 0개)")


if __name__ == "__main__":
    main()
