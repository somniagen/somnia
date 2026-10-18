import { createRawSnippet, mount, unmount } from 'svelte'
import { api } from './api'
import { live } from './live.svelte'
import { session } from './session.svelte'
import type { GalleryItem, PluginInfo, WsMessage } from './types'
import * as ui from './ui'

type Cleanup = (() => void) | void

export interface PluginPage {
  plugin: string
  id: string
  title: string
  icon: string
  // fills el, returns a cleanup
  mount: (el: HTMLElement) => Cleanup
}

export interface PluginImageAction {
  plugin: string
  id: string
  label: string
  icon: string
  run: (item: GalleryItem) => unknown
}

// what a plugin's web entry gets: `export default function activate(host) { ...; return cleanup }`
export interface PluginHost {
  id: string
  info: PluginInfo
  api: typeof api
  live: typeof live
  session: typeof session
  toast: typeof ui.toast
  // svelte primitives from lib/ui plus mount/unmount/createRawSnippet to render them
  ui: typeof ui & { mount: typeof mount; unmount: typeof unmount; createRawSnippet: typeof createRawSnippet }
  // url of a route the plugin's backend added to ctx.router
  url: (path: string) => string
  fetch: (path: string, init?: RequestInit) => Promise<Response>
  json: <T = unknown>(path: string, init?: RequestInit & { body?: unknown }) => Promise<T>
  // url of a file next to the web entry
  asset: (path: string) => string
  // events from ctx.broadcast(event, data)
  on: (event: string, fn: (data: unknown) => void) => () => void
  onMessage: (fn: (msg: WsMessage) => void) => () => void
  addPage: (page: Omit<PluginPage, 'plugin'>) => () => void
  addImageAction: (action: Omit<PluginImageAction, 'plugin'>) => () => void
  addStyle: (css: string) => () => void
  onCleanup: (fn: () => void) => void
}

interface Active {
  rev: string
  cleanups: (() => void)[]
}

class Plugins {
  list = $state.raw<PluginInfo[]>([])
  // raw so registrations keep their identity for removal
  pages = $state.raw<PluginPage[]>([])
  actions = $state.raw<PluginImageAction[]>([])
  errors = $state<Record<string, string>>({})
  private active = new Map<string, Active>()
  private started = false
  private syncing: Promise<void> = Promise.resolve()

  start() {
    if (this.started) return
    this.started = true
    live.on((m) => {
      if (m.type === 'plugins') this.set(m.plugins)
      else if (m.type === 'snapshot') void this.refresh()
    })
    void this.refresh()
  }

  async refresh() {
    try {
      this.set(await api.plugins())
    } catch {}
  }

  private set(list: PluginInfo[]) {
    this.list = list
    this.syncing = this.syncing.then(() => this.sync())
  }

  private async sync() {
    const want = new Map(this.list.filter((p) => p.enabled && p.loaded && p.web).map((p) => [p.id, p]))
    for (const [id, a] of this.active) {
      const p = want.get(id)
      if (!p || p.rev !== a.rev) this.deactivate(id)
    }
    for (const p of want.values()) {
      if (!this.active.has(p.id)) await this.activate(p)
    }
  }

  private deactivate(id: string) {
    const a = this.active.get(id)
    if (!a) return
    this.active.delete(id)
    for (const c of a.cleanups.reverse()) {
      try {
        c()
      } catch (e) {
        console.error(`[plugin ${id}] cleanup failed`, e)
      }
    }
    this.pages = this.pages.filter((x) => x.plugin !== id)
    this.actions = this.actions.filter((x) => x.plugin !== id)
  }

  private async activate(p: PluginInfo) {
    const a: Active = { rev: p.rev, cleanups: [] }
    this.active.set(p.id, a)
    const { [p.id]: _, ...rest } = this.errors
    this.errors = rest
    try {
      const mod = await import(/* @vite-ignore */ `/api/plugins/${p.id}/web/${p.web}?v=${encodeURIComponent(p.rev)}`)
      if (this.active.get(p.id) !== a) return
      const fn = mod.default ?? mod.activate
      if (typeof fn === 'function') {
        const c = await fn(this.host(p, a))
        if (typeof c === 'function') a.cleanups.push(c)
      }
    } catch (e) {
      console.error(`[plugin ${p.id}] failed to start`, e)
      this.errors = { ...this.errors, [p.id]: e instanceof Error ? e.message : String(e) }
    }
  }

  private host(p: PluginInfo, a: Active): PluginHost {
    const id = p.id
    const track = (c: () => void) => {
      a.cleanups.push(c)
      return c
    }
    const url = (path: string) => `/api/ext/${id}/${path.replace(/^\//, '')}`
    return {
      id,
      info: p,
      api,
      live,
      session,
      toast: ui.toast,
      ui: { ...ui, mount, unmount, createRawSnippet },
      url,
      fetch: (path, init) => fetch(url(path), init),
      json: async (path, init) => {
        const body = init?.body
        const plain = body !== undefined && !(body instanceof FormData) && typeof body !== 'string'
        const res = await fetch(url(path), {
          ...init,
          body: plain ? JSON.stringify(body) : (body as BodyInit | undefined),
          headers: plain ? { 'content-type': 'application/json', ...init?.headers } : init?.headers,
        })
        if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText)
        return res.json()
      },
      asset: (path) => `/api/plugins/${id}/web/${path.replace(/^\//, '')}`,
      on: (event, fn) => track(live.on((m) => m.type === 'plugin' && m.plugin === id && m.event === event && fn(m.data))),
      onMessage: (fn) => track(live.on(fn)),
      addPage: (page) => {
        const full = { ...page, plugin: id }
        this.pages = [...this.pages.filter((x) => !(x.plugin === id && x.id === page.id)), full]
        return track(() => (this.pages = this.pages.filter((x) => x !== full)))
      },
      addImageAction: (action) => {
        const full = { ...action, plugin: id }
        this.actions = [...this.actions.filter((x) => !(x.plugin === id && x.id === action.id)), full]
        return track(() => (this.actions = this.actions.filter((x) => x !== full)))
      },
      addStyle: (css) => {
        const el = document.createElement('style')
        el.dataset.plugin = id
        el.textContent = css
        document.head.append(el)
        return track(() => el.remove())
      },
      onCleanup: (fn) => void track(fn),
    }
  }

  page(plugin: string, id: string) {
    return this.pages.find((x) => x.plugin === plugin && x.id === id)
  }
}

export const plugins = new Plugins()
