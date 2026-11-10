"""모든 API 응답에 붙이는 보안 헤더.

화면(정적 파일)은 로컬 재현용 Nginx 가 같은 헤더를 붙인다(infrastructure/docker/compose/local/nginx.portfolio.conf, nginx-admin.conf).
이미 같은 헤더가 있으면 덮어쓰지 않는다(setdefault) — 특정 응답이 일부러 다르게 정한 값을 존중하기 위해.
"""
from flask import Flask, request

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",            # 내용 형식 추측(MIME sniffing) 금지
    "X-Frame-Options": "DENY",                      # 다른 사이트 iframe 안에 넣지 못하게 (클릭재킹)
    "Referrer-Policy": "strict-origin-when-cross-origin",  # 다른 사이트로 주소 전체를 넘기지 않음
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def init_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        # 로그인 상태·개인정보가 담긴 API 응답은 브라우저·프록시가 저장하지 않게
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
