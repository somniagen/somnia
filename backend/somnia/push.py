from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

from . import auth, config

CLAIMS = {"sub": "mailto:somnia@example.com"}
_lock = threading.Lock()
_vapid: Vapid01 | None = None
# images finished since the last queue notification
_pending = {"count": 0, "last": None}


def _key_file() -> Path:
    return config.DATA_DIR / "vapid_private.pem"


def _subs_file() -> Path:
    return config.DATA_DIR / "push_subscriptions.json"


def vapid() -> Vapid01:
    global _vapid
    with _lock:
        if _vapid is None:
            f = _key_file()
            if f.exists():
                _vapid = Vapid01.from_file(str(f))
            else:
                v = Vapid01()
                v.generate_keys()
                v.save_key(str(f))
                _vapid = v
        return _vapid


def public_key() -> str:
    raw = vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _load() -> list[dict]:
    f = _subs_file()
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return []


def _save(subs: list[dict]) -> None:
    _subs_file().write_text(json.dumps(subs, indent=2), "utf-8")


def subscriptions() -> list[dict]:
    with _lock:
        return _load()


def subscribe(sub: dict, label: str) -> dict:
    entry = {"endpoint": sub["endpoint"], "keys": sub["keys"], "label": label[:80], "createdAt": int(time.time() * 1000)}
    with _lock:
        subs = [s for s in _load() if s["endpoint"] != entry["endpoint"]]
        subs.append(entry)
        _save(subs)
    return entry


def unsubscribe(endpoint: str) -> bool:
    with _lock:
        subs = _load()
        keep = [s for s in subs if s["endpoint"] != endpoint]
        _save(keep)
    return len(keep) != len(subs)


def image_sig(item_id: str) -> str:
    return hmac.new(auth._secret(), b"push-image:" + item_id.encode(), hashlib.sha256).hexdigest()[:32]


def image_path(item_id: str, sig: str) -> Path | None:
    if not hmac.compare_digest(sig, image_sig(item_id)) or "/" in item_id or "\\" in item_id or ".." in item_id:
        return None
    f = Path(config.settings().outputDir) / "thumbs" / f"{item_id}.webp"
    return f if f.is_file() else None


def send(payload: dict, only: str | None = None) -> int:
    v = vapid()
    data = json.dumps(payload)
    sent = 0
    gone: list[str] = []
    for s in subscriptions():
        if only and s["endpoint"] != only:
            continue
        try:
            webpush({"endpoint": s["endpoint"], "keys": s["keys"]}, data, vapid_private_key=v,
                    vapid_claims=dict(CLAIMS), ttl=86400, headers={"Urgency": "normal"}, timeout=15)
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):
                gone.append(s["endpoint"])
            else:
                print(f"[somnia] push to {s.get('label') or 'device'} failed: {e}")
        except Exception as e:
            print(f"[somnia] push failed: {e}")
    for ep in gone:
        unsubscribe(ep)
    return sent


def send_async(payload: dict) -> None:
    if subscriptions():
        threading.Thread(target=send, args=(payload,), name="somnia-push", daemon=True).start()


def on_finish(job: dict, drained: bool) -> None:
    if job.get("status") == "done":
        imgs = job.get("images") or []
        _pending["count"] += len(imgs)
        if imgs:
            _pending["last"] = imgs[-1]
    elif job.get("status") == "error":
        send_async({"title": "Generation failed", "body": (job.get("error") or "Unknown error")[:180], "tag": "somnia-error", "url": "/"})
    if not drained or not _pending["count"]:
        return
    n, last = _pending["count"], _pending["last"]
    _pending["count"], _pending["last"] = 0, None
    msg = {"title": "Queue finished", "body": f"{n} image{'s' if n != 1 else ''}", "tag": "somnia-queue", "url": "/#/gallery"}
    if last and last.get("id"):
        u = f"/api/push/image/{last['id']}?sig={image_sig(last['id'])}"
        msg["image"] = u
        msg["icon"] = u
    send_async(msg)
