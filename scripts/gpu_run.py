import msvcrt
import subprocess
import sys
import time
from pathlib import Path

lock = Path(__file__).resolve().parents[1] / "data" / "gpu.lock"
lock.parent.mkdir(exist_ok=True)
with open(lock, "a+") as f:
    while True:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            time.sleep(2)
    try:
        sys.exit(subprocess.call(sys.argv[1:]))
    finally:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
