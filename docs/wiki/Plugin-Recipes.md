# Plugin recipes

Complete plugins you can drop into `plugins/<name>/`. Each also needs a `plugin.json`, e.g. `{ "name": "Wildcards" }`.

## Wildcards

Replaces `__name__` in prompts with a random line from `wildcards/name.txt` in the plugin folder.

`plugin.py`:

```python
import random
import re

PATTERN = re.compile(r"__([\w/-]+)__")


def setup(ctx):
    folder = ctx.dir / "wildcards"

    def pick(m):
        f = folder / f"{m.group(1)}.txt"
        if not f.is_file():
            return m.group(0)
        lines = [x.strip() for x in f.read_text("utf-8").splitlines() if x.strip() and not x.startswith("#")]
        return random.choice(lines) if lines else ""

    def expand(params):
        for key in ("prompt", "negative"):
            if isinstance(params.get(key), str):
                params[key] = PATTERN.sub(pick, params[key])

    ctx.on_submit(expand)
```

`wildcards/hair.txt`:

```
long hair
short hair
twintails
```

Prompt: `1girl, __hair__, smile`. The prompt editor segments are left alone, so reusing an image's params brings back `__hair__` and rolls again. Editing a `.txt` file reloads the plugin, which is harmless here.

`on_submit` runs once per submit, so a batch of 4 shares one pick. Queue images one at a time for a new pick each.

## Image color action

An image action that asks the backend for the image's average color.

`plugin.py`:

```python
from pathlib import Path

from fastapi import HTTPException
from PIL import Image

from somnia import config


def setup(ctx):
    @ctx.router.get("/color")
    def color(url: str):
        name = url.split("?")[0].removeprefix("/outputs/")
        root = Path(config.settings().outputDir).resolve()
        f = (root / name).resolve()
        if root not in f.parents or not f.is_file():
            raise HTTPException(404, "image not found")
        r, g, b = Image.open(f).convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        return {"hex": f"#{r:02x}{g:02x}{b:02x}"}
```

`web/index.js`:

```js
export default function activate(host) {
  host.addImageAction({
    id: 'color',
    label: 'Average color',
    icon: 'palette',
    run: async (item) => {
      const { hex } = await host.json(`/color?url=${encodeURIComponent(item.url)}`)
      await navigator.clipboard.writeText(hex)
      host.toast.success(`${hex} copied`)
    },
  })
}
```

`url` comes from the client: always resolve paths and check they stay inside the folder you expect, as above.

## Settings page with primitives

A page with a toggle whose value is stored on the server and synced across devices.

`plugin.py`:

```python
from fastapi import Body


def setup(ctx):
    @ctx.router.get("/settings")
    def get():
        return {"enabled": False, **ctx.settings()}

    @ctx.router.put("/settings")
    def put(body: dict = Body(...)):
        s = {**ctx.settings(), **body}
        ctx.save_settings(s)
        ctx.broadcast("settings", s)
        return s
```

`web/index.js`:

```js
export default function activate(host) {
  const { ui } = host
  host.addStyle('.my-settings { display: flex; flex-direction: column; gap: var(--sp-3); padding: var(--sp-5); max-width: 520px; }')

  host.addPage({
    id: 'settings',
    title: 'My plugin',
    icon: 'tune',
    mount(el) {
      el.innerHTML = '<div class="my-settings"><h2>My plugin</h2><div class="t"></div></div>'
      let toggle
      const render = (s) => {
        if (toggle) ui.unmount(toggle)
        toggle = ui.mount(ui.Toggle, {
          target: el.querySelector('.t'),
          props: {
            label: 'Enabled',
            checked: s.enabled,
            onchange: (v) => host.json('/settings', { method: 'PUT', body: { enabled: v } }),
          },
        })
      }
      host.json('/settings').then(render)
      // keeps other devices in sync
      const off = host.on('settings', render)
      return () => {
        off()
        if (toggle) ui.unmount(toggle)
      }
    },
  })
}
```

## Queue finished webhook

Posts to a url (ntfy, Discord, Home Assistant...) when the queue drains. The url is read from the plugin's settings file `data/plugins/<id>/settings.json`, e.g. `{"url": "https://ntfy.sh/my-topic"}`.

`plugin.py`:

```python
import httpx


def setup(ctx):
    def finished(job, drained):
        url = ctx.settings().get("url")
        if not (drained and url):
            return

        def send(stop):
            try:
                httpx.post(url, content=f"Somnia queue finished ({job['status']})", timeout=10)
            except httpx.HTTPError as e:
                ctx.log("webhook failed:", e)

        ctx.thread(send, "webhook")

    ctx.on_job_finish(finished)
```

The request runs on its own thread so the queue does not wait for the network.

## Periodic task

```python
def setup(ctx):
    def loop(stop):
        while not stop.wait(300):
            ctx.log("still alive")

    ctx.thread(loop, "heartbeat")
```

The thread ends within one `wait` interval of the plugin being reloaded or disabled.

## Live progress page

A page that mirrors the current generation from websocket messages.

```js
export default function activate(host) {
  host.addPage({
    id: 'progress',
    title: 'Progress',
    icon: 'monitoring',
    mount(el) {
      el.innerHTML = '<pre style="padding: var(--sp-5); color: var(--text-muted)"></pre>'
      const pre = el.querySelector('pre')
      const show = () => {
        const c = host.live.current
        pre.textContent = c ? `${c.phase} ${c.step}/${c.total} (${Math.round(c.overall * 100)}%)` : 'idle'
      }
      show()
      return host.onMessage((m) => {
        if (m.type === 'progress' || m.type === 'done' || m.type === 'queue') show()
      })
    },
  })
}
```
