# Plugin backend API

The backend is `plugin.py` in the plugin folder. It is optional; a plugin can be frontend only.

## Module

`plugin.py` is imported as the package `somnia_plugins.<id>` with the plugin folder as its package path, so sibling files import relatively:

```python
from . import helpers
from .db import open_db
```

Recognized module members, all optional:

```python
from fastapi import APIRouter

router = APIRouter()     # merged with ctx.router

def setup(ctx): ...      # called after import
def teardown(ctx): ...   # called before unload or reload
```

On every reload the module and all its submodules are dropped from `sys.modules` and imported fresh, so **module level state starts over**. Persist anything you want to keep (see `ctx.settings`).

If the import or `setup` raises, the error shows in Settings > Plugins and the full traceback is printed to the server console. Whatever `setup` registered before failing is cleaned up again.

You can import Somnia's own modules (`from somnia import config, models, jobs`). They are not a stable API and may change between versions; prefer `ctx` where it covers what you need.

## ctx

`setup` and `teardown` receive a `Context`. Everything registered through it is undone automatically on unload.

### Attributes

| | |
|---|---|
| `ctx.id` | plugin id (folder name) |
| `ctx.dir` | `Path` of the plugin folder |
| `ctx.manifest` | parsed `plugin.json` |
| `ctx.data_dir` | `Path` of `data/plugins/<id>/` for files you write; created by `save_settings`, otherwise `mkdir` it yourself |
| `ctx.router` | `fastapi.APIRouter` served at `/api/ext/<id>` |

### ctx.router

```python
@ctx.router.get("/items/{item_id}")
async def item(item_id: str, full: bool = False): ...

@ctx.router.post("/run")
def run(body: RunBody): ...
```

Routes are reachable at `/api/ext/<id>/<path>`. Requests go through the LAN toggle and LAN password like every `/api` route. While a plugin is not loaded its routes answer `404 {"detail": "plugin not loaded"}`. Websocket routes work too.

### ctx.on_job_finish(fn)

```python
def fn(job: dict, drained: bool) -> None
```

Called on the worker thread after every job ends, whatever its status. `job` has `id`, `params`, `status` (`done`, `error`, `cancelled`), `createdAt`, `startedAt`, `finishedAt`, `images` (gallery item dicts with `id`, `url`, `thumbUrl`, `width`, `height`, `seed`, `params`) and `error`. Grid cells also carry `grid`. `drained` is true when nothing is left in the queue.

Exceptions are caught and printed. Keep the function quick, the next job waits for it; hand slow work to `ctx.thread`.

### ctx.on_submit(fn)

```python
def fn(params: dict) -> dict | None
```

Called when jobs are queued, before seeds are assigned. Return a new params dict, or change `params` in place and return `None`. `params` is the `GenParams` json (`prompt`, `negative`, `model`, `steps`, `cfg`, `width`, `height`, `seed`, `loras`, ...; see `web/src/lib/types.ts`). Only `prompt` and `negative` are used for generation; `segments` is what the prompt editor restores when an image is reused.

It runs **once per submit**, not once per job: queueing 4 images, or an x/y/z grid, calls it once and all jobs share the result. Repeating jobs ("repeat until stopped") call it again for each copy, with the params the first call produced.

### ctx.thread(fn, name="worker")

```python
def fn(stop: threading.Event) -> None
```

Starts a daemon thread and returns its stop event, which is set on unload. Loop on `stop.wait(seconds)` so the thread exits promptly:

```python
def poll(stop):
    while not stop.wait(60):
        ...

ctx.thread(poll)
```

Threads you start yourself are not stopped on reload, so every save would add another one.

### ctx.broadcast(event, data=None)

Sends `{type: "plugin", plugin: <id>, event, data}` to every connected browser. `data` must be json serializable. Safe from any thread. Receive it with `host.on(event, fn)`.

### ctx.settings() / ctx.save_settings(data)

Read and write a json dict at `data/plugins/<id>/settings.json`. `settings()` returns `{}` when nothing is saved. This lives outside the plugin folder, so writing it does not trigger a reload.

### ctx.on_cleanup(fn)

Runs `fn()` on unload, after `teardown`, in reverse registration order. Use it for anything you opened yourself: files, sockets, subprocesses, hooks into Somnia internals.

### ctx.log(*args)

Prints `[plugin <id>] ...` to the server console.

## Dependencies

Plugins run in Somnia's Python environment (`.venv`, Python 3.12), so everything Somnia depends on is importable: `fastapi`, `pydantic`, `httpx`, `PIL`, `numpy`, `torch`, `onnxruntime`... Anything else has to be installed into `.venv` by the user (`uv pip install --python .venv <package>`) and is removed again by the next `uv sync` or reinstall. Prefer vendoring small pure Python dependencies into the plugin folder and importing them relatively.
