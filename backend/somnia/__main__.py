import uvicorn

from . import config
from .app import create_app


def main() -> None:
    uvicorn.run(create_app(), host="0.0.0.0", port=config.settings().port, log_level="info")


if __name__ == "__main__":
    main()
