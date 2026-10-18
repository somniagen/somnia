# Plugins

Somnia plugins add backend routes, job hooks, pages and image actions to the app. They are plain folders: no build step, no package manager, and **no restart**. Save a file and the plugin reloads in the server and in every open browser within about a second.

- [Quickstart](Plugin-Quickstart): a working plugin in five minutes
- [Backend API](Plugin-Backend-API): `plugin.py`, `ctx`, routes and hooks
- [Frontend API](Plugin-Frontend-API): `web/index.js`, `host`, pages and actions
- [Recipes](Plugin-Recipes): wildcards, image actions with a backend, settings pages, background tasks
- [Troubleshooting](Plugin-Troubleshooting)

## How it works

Plugins live in the `plugins/` folder at the root of your Somnia install, next to `backend/` and `web/`. It is created on first start and ignored by git.

```
somnia/
  plugins/
    hello/
      plugin.json     required
      plugin.py       optional backend
      web/
        index.js      optional frontend
        more.js       anything the entry imports
```

Every second the server checks each plugin folder for changes (file count and newest modification time, ignoring `__pycache__` and `node_modules`). When something changed:

1. The old version is torn down: `teardown(ctx)` runs, every hook registered through `ctx` is removed, its routes disappear and its Python modules are dropped from `sys.modules`.
2. The new version is imported and `setup(ctx)` runs.
3. The server broadcasts the new plugin list over the websocket.
4. Every open browser runs the old frontend's cleanups and imports the new `web/index.js`.

Adding a folder loads it, deleting a folder unloads it. Nothing else in the app restarts: the queue, the running generation and loaded models are untouched.

## plugin.json

```json
{
  "name": "Hello",
  "version": "0.1.0",
  "description": "Shown behind the (i) in Settings > Plugins.",
  "web": "web/index.js"
}
```

| Field | Default | |
|---|---|---|
| `name` | folder name | display name |
| `version` | `""` | shown next to the name |
| `description` | `""` | |
| `web` | `web/index.js` | frontend entry, relative to the plugin folder |

The **folder name is the plugin id**. It must match `^[a-z0-9][a-z0-9_-]{0,63}$`; other folders are ignored. The id appears in urls (`/api/ext/<id>/...`, `#/p/<id>/...`), so keep it short.

## Managing plugins

**Settings > Plugins** lists every plugin with its status (green when loaded, red with the error when it failed), a link to each page it registered, a reload button and an enable toggle. New plugins are enabled by default; the toggle state is kept in `data/plugins.json`.

Enabling, disabling, reloading and rescanning only work from the machine running Somnia (requests from the LAN get 403), like other settings.

## Security

A plugin is Python code running inside the server and JavaScript running in every browser that opens the UI, with full access to your files, models, gallery and network. **Only install plugins you trust and have read.** Plugin routes sit under `/api`, so they are covered by the LAN toggle and the LAN password like the rest of the app.

## Example

A complete example (a page, an image action, two routes and a job hook) ships in the repository at `docs/plugin-example`. Copy it to `plugins/hello/` to try it.
