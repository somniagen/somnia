# Plugin quickstart

This builds a plugin with a backend route, a page, an image action and a job hook. Keep Somnia running the whole time.

## 1. Create the folder

`plugins/hello/plugin.json`:

```json
{ "name": "Hello", "version": "0.1.0", "description": "My first plugin" }
```

Open **Settings > Plugins**: "Hello" appears within a second. It does nothing yet.

## 2. Add a backend route

`plugins/hello/plugin.py`:

```python
def setup(ctx):
    @ctx.router.get("/greet")
    def greet(name: str = "world"):
        return {"message": f"hello {name}"}
```

Save, then open `http://localhost:7865/api/ext/hello/greet?name=somnia`:

```json
{"message": "hello somnia"}
```

Change the message and save again. Reload the url: the new text is there, no restart. `ctx.router` is a normal FastAPI `APIRouter`, so path params, query params, pydantic bodies and `async def` all work.

## 3. Add a page

`plugins/hello/web/index.js`:

```js
export default function activate(host) {
  host.addPage({
    id: 'main',
    title: 'Hello',
    icon: 'waving_hand',
    mount(el) {
      el.innerHTML = '<div style="padding: var(--sp-5)"><h2>Hello</h2><p class="msg"></p></div>'
      host.json('/greet?name=page').then((r) => (el.querySelector('.msg').textContent = r.message))
    },
  })
}
```

A waving hand appears in the left rail (on phones the page is linked from Settings > Plugins). It opens `#/p/hello/main`. Edit the heading and save: the page re-renders in place.

`icon` is any [Material Symbols](https://fonts.google.com/icons) name.

## 4. Add an image action

Add to `activate`:

```js
  host.addImageAction({
    id: 'seed',
    label: 'Copy seed',
    icon: 'tag',
    run: async (item) => {
      await navigator.clipboard.writeText(String(item.seed))
      host.toast.success('Seed copied')
    },
  })
```

Generate an image or open one in the gallery: the new button sits next to Download.

## 5. Hook into generation

In `plugin.py`, inside `setup`:

```python
    def finished(job, drained):
        if job["status"] == "done":
            ctx.log("finished", job["id"], len(job["images"]), "images")
            ctx.broadcast("finished", {"id": job["id"]})

    ctx.on_job_finish(finished)
```

and in `activate`:

```js
  host.on('finished', (data) => host.toast.info(`Job ${data.id} done`))
```

Every finished job now logs to the server console and shows a toast in every open browser.

## Next

- [Backend API](Plugin-Backend-API) for everything `ctx` can do
- [Frontend API](Plugin-Frontend-API) for everything `host` can do
- [Recipes](Plugin-Recipes) for bigger examples
