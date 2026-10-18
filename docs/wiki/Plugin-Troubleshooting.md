# Plugin troubleshooting

**The plugin does not show up.** The folder must be directly inside `plugins/`, contain `plugin.json`, and have a lowercase id as its name (`a-z`, `0-9`, `_`, `-`, starting with a letter or digit). The refresh button in Settings > Plugins rescans immediately.

**It shows red.** The message is the exception from importing `plugin.py` or from `setup`. The full traceback is in the server console, prefixed with `[plugin <id>]`. Fix and save; it retries on every change.

**The page or action is missing although the plugin is green.** Frontend errors do not reach the server; open the browser console and look for `[plugin <id>] failed to start`. Common causes: a bare import (`import x from 'pkg'`), a syntax error, `activate` not exported as default or as `activate`, or `web` in `plugin.json` pointing to a missing file.

**It reloads over and over.** Something writes into the plugin folder (logs, caches, a database), and every write counts as a change. Write to `ctx.data_dir` instead. Only `__pycache__` and `node_modules` are ignored.

**State is lost after editing.** Expected: a reload re-imports the module. Keep state in `ctx.settings()` or in files under `ctx.data_dir`.

**Things run twice after a reload.** A thread, hook or listener was registered without going through `ctx` / `host` and survived the old version. Use `ctx.thread`, `ctx.on_job_finish`, `ctx.on_submit` and `ctx.on_cleanup` on the backend; `host.on`, `host.onMessage`, `host.onCleanup`, or the cleanup returned from `activate` / `mount` on the frontend (for `setInterval`, `window.addEventListener` and similar).

**A changed helper module is not picked up in the browser.** The entry is re-imported with a new `?v=`, but modules it imports keep their url and stay cached. Import them with `?v=${host.info.rev}` (see [Frontend API](Plugin-Frontend-API#activatehost)).

**`404 plugin not loaded`.** The plugin is disabled, failed to load, or the url is wrong: routes live at `/api/ext/<id>/<route path>`.

**`403` when toggling or reloading.** Plugins can only be managed from the machine running Somnia.

**`ModuleNotFoundError` for a package.** Plugins only see Somnia's `.venv`. See [Dependencies](Plugin-Backend-API#dependencies).

**Pages are missing on my phone.** Plugins load on every device, but pages are not in the phone tab bar. Open them from Settings > Plugins.
