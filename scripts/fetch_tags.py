import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from somnia import tags

if __name__ == "__main__":
    path = tags.download_csv()
    print(f"{path} ({path.stat().st_size // 1024} KB)")
