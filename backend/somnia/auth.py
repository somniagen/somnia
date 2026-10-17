from __future__ import annotations

import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie

from . import config, net

COOKIE = "somnia_auth"
MASK = "****"
_N, _R, _P = 2**14, 8, 1


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(pw: str) -> bool:
    stored = config.settings().lanPassword
    try:
        kind, salt, want = stored.split("$")
    except ValueError:
        return False
    if kind != "scrypt":
        return False
    h = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P, dklen=32)
    return hmac.compare_digest(h.hex(), want)


def _secret() -> bytes:
    f = config.DATA_DIR / "auth_secret"
    if not f.exists():
        f.write_text(secrets.token_hex(32), "utf-8")
    return bytes.fromhex(f.read_text("utf-8").strip())


def token() -> str:
    # bound to the stored hash, so changing the password drops every session
    return hmac.new(_secret(), b"session:" + config.settings().lanPassword.encode(), hashlib.sha256).hexdigest()


def enabled() -> bool:
    return bool(config.settings().lanPassword)


def valid(cookie: str | None) -> bool:
    return bool(cookie) and hmac.compare_digest(cookie, token())


def cookie_from_headers(headers: list[tuple[bytes, bytes]]) -> str | None:
    for k, v in headers:
        if k == b"cookie":
            c = SimpleCookie()
            try:
                c.load(v.decode("latin-1"))
            except Exception:
                continue
            if COOKIE in c:
                return c[COOKIE].value
    return None


def allowed(scope) -> bool:
    if not enabled():
        return True
    client = scope.get("client")
    if net.is_loopback(client[0] if client else None):
        return True
    return valid(cookie_from_headers(scope.get("headers") or []))


def protected(path: str) -> bool:
    if path.startswith(("/api/auth", "/api/push/image/")):
        return False
    return path.startswith(("/api/", "/outputs/", "/files/")) or path in ("/api", "/ws")
