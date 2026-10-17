from __future__ import annotations

import socket
from pathlib import Path


def lan_ips() -> list[str]:
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    out: list[str] = []
    for ip in ips:
        if ip.startswith("127.") or ip.startswith("169.254.") or ip in out:
            continue
        out.append(ip)
    return out


def tls_files() -> tuple[str, str] | None:
    from . import config

    s = config.settings()
    if s.httpsCert and s.httpsKey and Path(s.httpsCert).is_file() and Path(s.httpsKey).is_file():
        return s.httpsCert, s.httpsKey
    return None


# set by __main__ when uvicorn serves tls
SCHEME = "http"


def lan_urls(port: int) -> list[str]:
    return [f"{SCHEME}://{ip}:{port}" for ip in lan_ips()]


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    return host in ("127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1", "testclient")
