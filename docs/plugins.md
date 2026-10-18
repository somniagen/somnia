# Plugins

A plugin is a folder in `plugins/` (next to `backend/` and `web/`) containing a `plugin.json`. Somnia polls the folder every second: adding, editing or deleting any file loads, reloads or unloads that plugin live, without restarting the server or reloading the page. Folder names are the plugin id (`a-z 0-9 _ -`). A working example is in `docs/plugin-example/` (copy it to `plugins/hello/`).

```
plugins/hello/
  plugin.json      {"name", "version", "description", "web"?}  (web defaults to "web/index.js")
  plugin.py        optional backend
  web/index.js     optional frontend (ES module, plain js, no build step)
```

Plugins run with full access to the machine. Only install code you trust. Enable/disable and reload are in Settings > Plugins (`#/settings/plugins`) (state in `data/plugins.json`); management is loopback only.

## Backend (`plugin.py`)

Imported as the package `somnia_plugins.<id>`, so relative imports of sibling files work. All of it is re-imported on every reload.

```python
def setup(ctx): ...      # optional, called on load
def teardown(ctx): ...   # optional, called before unload/reload
router = APIRouter()     # optional, same as adding routes to ctx.router
```

`ctx` (`somnia.plugins.Context`):
- `ctx.router`: an `APIRouter` served at `/api/ext/<id>/...` (same auth as the rest of `/api`).
- `ctx.on_job_finish(fn)`: `fn(job, drained)` on the worker thread after each job.
- `ctx.on_submit(fn)`: `fn(params)` before jobs are queued; return new params or mutate in place.
- `ctx.thread(fn)`: runs `fn(stop_event)` on a daemon thread, `stop_event` is set on unload.
- `ctx.broadcast(event, data)`: websocket message `{type:'plugin', plugin, event, data}`.
- `ctx.settings()` / `ctx.save_settings(dict)`: json in `ctx.data_dir` (`data/plugins/<id>/`).
- `ctx.on_cleanup(fn)`, `ctx.log(...)`, `ctx.id`, `ctx.dir`, `ctx.manifest`.

Hooks registered through `ctx` are removed on unload. A failing import or `setup` is shown in Settings with the error; the previous version is already unloaded.

## Frontend (`web/index.js`)

```js
export default function activate(host) {
  // register things, optionally return a cleanup function
}
```

Everything registered through `host` is undone when the plugin reloads or is disabled. `host`:
- `addPage({ id, title, icon, mount(el) => cleanup })`: a page at `#/p/<plugin>/<id>`, shown in the desktop rail and in Settings > Plugins.
- `addImageAction({ id, label, icon, run(item) })`: a button in the image actions (generate preview, lightbox).
- `addStyle(css)`: injects a stylesheet (use the tokens from `lib/ui/tokens.css`).
- `url(path)`, `fetch(path, init)`, `json(path, { method, body })`: call the plugin's backend routes.
- `asset(path)`: url of a file next to the web entry (imports of siblings work too).
- `on(event, fn)`: plugin events from `ctx.broadcast`; `onMessage(fn)`: every websocket message.
- `api`, `live`, `session`, `toast`: the app's rest client, live state, prompt/params session and toasts.
- `ui`: the `lib/ui` primitives plus svelte's `mount`, `unmount`, `createRawSnippet`, e.g. `ui.mount(ui.Button, { target, props })`.
- `onCleanup(fn)`, `id`, `info`.
