import uvicorn

from . import config, net
from .app import create_app


def main() -> None:
    tls = net.tls_files()
    kw = {}
    if tls:
        net.SCHEME = "https"
        kw = {"ssl_certfile": tls[0], "ssl_keyfile": tls[1]}
    uvicorn.run(create_app(), host="0.0.0.0", port=config.settings().port, log_level="info", **kw)


if __name__ == "__main__":
    main()
