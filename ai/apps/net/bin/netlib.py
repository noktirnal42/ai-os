"""Shared opt-in network policy for the small Phase 2 network utilities."""
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

def allowed_hosts() -> set[str]:
    return {item.strip().lower() for item in os.environ.get(
        "AIOS_FETCH_ALLOWLIST", "10.0.2.2,127.0.0.1,localhost"
    ).split(",") if item.strip()}

def validate_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password or host not in allowed_hosts():
        raise ValueError("scheme, credentials, or host is outside the allowlist")
    return parsed

class AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            validate_url(newurl)
        except ValueError as exc:
            raise urllib.error.HTTPError(newurl, code, str(exc), headers, fp) from exc
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(AllowlistRedirectHandler())

def resolve(host: str, port: int) -> list[str]:
    found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({item[4][0] for item in found})
