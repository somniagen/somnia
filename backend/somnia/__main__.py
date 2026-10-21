import os

# ops metal lacks run on the cpu instead of failing, must be set before torch loads
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import uvicorn  # noqa: E402

from . import config, net  # noqa: E402
from .app import create_app  # noqa: E402


def main() -> None:
    tls = net.tls_files()
    kw = {}
    if tls:
        net.SCHEME = "https"
        kw = {"ssl_certfile": tls[0], "ssl_keyfile": tls[1]}
    uvicorn.run(create_app(), host="0.0.0.0", port=config.settings().port, log_level="info", **kw)


if __name__ == "__main__":
    main()
