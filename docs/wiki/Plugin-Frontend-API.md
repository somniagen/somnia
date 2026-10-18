# Plugin frontend API

The frontend is an ES module, by default `web/index.js` (see `web` in [plugin.json](Plugins#pluginjson)). The browser loads it as is: plain JavaScript, no TypeScript, no JSX, no bare imports (`import x from 'lodash'` does not work). Relative imports of files next to the entry work:

```js
import { render } from './render.js'
```

## activate(host)

```js
export default function activate(host) {
  // ...
  return () => { /* optional cleanup */ }
}
```

A named `export function activate` works too, and `activate` may be async. It runs once per page load and again after each reload of the plugin. Before a reload, everything registered through `host` is removed and the returned cleanup runs, so you rarely need one.

The entry is imported with a `?v=<rev>` query that changes whenever any plugin file changes, which defeats the browser cache. Modules the entry imports keep their url and stay cached; if they change often, import them dynamically with the same query: ``await import(`./render.js?v=${host.info.rev}`)``.

## Pages

### host.addPage({ id, title, icon, mount })

```js
host.addPage({
  id: 'main',               // url: #/p/<plugin>/<id>
  title: 'Hello',           // rail tooltip
  icon: 'waving_hand',      // material symbol
  mount(el) {               // el is an empty div filling the main area
    // render into el
    return () => {}         // optional cleanup when leaving the page
  },
})
```

Pages show in the desktop rail (above Settings) and as links in Settings > Plugins, which is how phones reach them. `el` scrolls and is emptied after your cleanup runs. `mount` runs each time the page is opened. Returns a function that removes the page.

## Image actions

### host.addImageAction({ id, label, icon, run })

```js
host.addImageAction({ id: 'seed', label: 'Copy seed', icon: 'tag', run: async (item) => { ... } })
```

Adds a button to the image action bar under the generate preview and in the gallery lightbox. `run(item)` gets the `GalleryItem` (`id`, `url`, `thumbUrl`, `width`, `height`, `seed`, `params`, `createdAt`, ...). A thrown error becomes an error toast. Returns a remover.

## Talking to your backend

| | |
|---|---|
| `host.url(path)` | `/api/ext/<id>/<path>` |
| `host.fetch(path, init)` | `fetch(host.url(path), init)` |
| `host.json(path, { method, body, headers })` | fetch that json encodes a plain object `body`, throws `Error(detail)` on non 2xx and returns the parsed json |
| `host.asset(path)` | url of a file next to the web entry, for images, css or workers |

```js
const stats = await host.json('/stats')
await host.json('/run', { method: 'POST', body: { prompt: 'cat' } })
```

## Events

| | |
|---|---|
| `host.on(event, fn)` | `fn(data)` for `ctx.broadcast(event, data)` from this plugin's backend |
| `host.onMessage(fn)` | every websocket message (`progress`, `done`, `queue`, `download`, ...; see `WsMessage` in `web/src/lib/types.ts`) |

Both return an unsubscribe function and are unsubscribed on reload.

## App state

| | |
|---|---|
| `host.api` | the typed rest client (`web/src/lib/api.ts`), e.g. `host.api.gallery()`, `host.api.queue(params, count)`, `host.api.models()` |
| `host.live` | live state: `queue`, `current` (progress), `preview`, `recent`, `downloads`, `connected`, `settings` |
| `host.session` | the Generate tab: `params`, `update(patch)`, `applyParams(params)`, `setPrompt(positive, negative?)`, `addBoilerplate(text, 'positive' or 'negative')`, `addLora(id, weight)`, `generate(count?)` |
| `host.toast` | `success(msg, opts)`, `error`, `info`; opts `{ description, action: { label, run }, duration }` |
| `host.info` | this plugin's `PluginInfo` (`id`, `name`, `version`, `rev`, ...) |
| `host.id` | plugin id |
| `host.onCleanup(fn)` | runs `fn` when the plugin reloads or is disabled |

`host.live` and `host.session` are Svelte state objects: read them when you need a value, and use `host.onMessage` to know when to read again.

## Styling

`host.addStyle(css)` injects a `<style>` and returns a remover. Use Somnia's design tokens so plugins match the app: `--bg`, `--surface-1..4`, `--grad-1..4`, `--sheen`, `--hairline`, `--text`, `--text-muted`, `--text-faint`, `--danger`, `--success`, `--warning`, `--sp-1..6`, `--r-sm`, `--r-md`, `--r-lg`, `--fs-xs`, `--fs-sm`, `--font`, `--font-mono` (all in `web/src/lib/ui/tokens.css`). `<span class="icon">name</span>` renders a Material Symbol.

The styles are global, so prefix your selectors with a class of your page.

## UI primitives

`host.ui` holds Somnia's Svelte components (`Button`, `IconButton`, `Toggle`, `Slider`, `NumberField`, `Select`, `Segmented`, `Card`, `Surface`, `Field`, `Chip`, `EmptyState`, `Spinner`, ...; props in `web/src/lib/ui/README.md`) plus Svelte's `mount`, `unmount` and `createRawSnippet` to render them from plain JavaScript:

```js
const { ui } = host
const btn = ui.mount(ui.Button, {
  target: el,
  props: {
    variant: 'primary',
    icon: 'play_arrow',
    onclick: () => host.toast.info('clicked'),
    children: ui.createRawSnippet(() => ({ render: () => '<span>Run</span>' })),
  },
})
// later, e.g. in the page cleanup
ui.unmount(btn)
```

Text content (`children`) is passed as a snippet whose `render` returns html with a single root element. Props passed this way are not reactive: to change one, unmount and mount again, and read user input back through callbacks (`onchange`, `onclick`). Unmount what you mount in your page's cleanup.
