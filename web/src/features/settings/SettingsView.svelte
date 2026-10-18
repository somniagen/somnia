<script lang="ts">
  import QRCode from 'qrcode'
  import TextInput from '$features/shell/TextInput.svelte'
  import { ApiError, api } from '$lib/api'
  import { editors } from '$lib/editors.svelte'
  import { live } from '$lib/live.svelte'
  import type { NetInfo, Settings } from '$lib/types'
  import { Button, Card, EmptyState, Field, IconButton, InfoTip, NumberField, SearchField, Select, Skeleton, Tabs, Toggle, mobile, reducedMotion, toast } from '$lib/ui'
  import { tick } from 'svelte'
  import Logo from '$features/shell/Logo.svelte'
  import LanSecurity from './LanSecurity.svelte'
  import NotificationsCard from './NotificationsCard.svelte'
  import PluginsCard from './PluginsCard.svelte'
  import { applyFind, clearFind, type FindResult } from './find'

  let s = $state<Settings | null>(null)
  let net = $state<NetInfo | null>(null)
  let error = $state('')
  let denied = $state(false)
  let token = $state('')
  let hfToken = $state('')
  let qrFor = $state(0)
  let qr = $state('')

  const local = ['localhost', '127.0.0.1', '[::1]', '::1'].includes(location.hostname)
  const readonly = $derived(!local || denied)

  async function load() {
    error = ''
    try {
      s = await api.settings()
      token = s.civitaiToken
      hfToken = s.hfToken
      net = await api.net()
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }
  $effect(() => {
    load()
  })

  $effect(() => {
    const ls = live.settings
    if (ls && s) {
      s = ls
      api.net().then((n) => (net = n), () => {})
    }
  })

  async function save(patch: Partial<Settings>) {
    if (readonly || !s) return
    try {
      s = await api.updateSettings(patch)
      if ('lanEnabled' in patch) net = await api.net()
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) denied = true
      toast.error('Not saved', { description: e instanceof Error ? e.message : String(e) })
      await load()
    }
  }

  function saveToken() {
    if (!s || token === s.civitaiToken) return
    save({ civitaiToken: token })
  }
  function saveHfToken() {
    if (!s || hfToken === s.hfToken) return
    save({ hfToken })
  }
  function setRoot(i: number, v: string) {
    if (!s) return
    const roots = [...s.modelRoots]
    roots[i] = v.trim()
    save({ modelRoots: roots.filter(Boolean) })
  }
  function removeRoot(i: number) {
    if (!s) return
    save({ modelRoots: s.modelRoots.filter((_, k) => k !== i) })
  }
  let newRoot = $state('')
  function addRoot() {
    if (!s || !newRoot.trim()) return
    save({ modelRoots: [...s.modelRoots, newRoot.trim()] })
    newRoot = ''
  }

  $effect(() => {
    editors.load()
  })
  let newEditor = $state('')
  let browsing = $state(false)

  async function editorCall(p: Promise<unknown>) {
    try {
      await p
    } catch (e) {
      toast.error('Not saved', { description: e instanceof Error ? e.message : String(e) })
    }
  }
  function addEditor(path = newEditor) {
    if (!path.trim()) return
    editorCall(editors.apply(api.addEditor(path.trim())).then(() => (newEditor = '')))
  }
  async function browseEditor() {
    browsing = true
    try {
      const r = await api.browseEditor()
      if (r.path) addEditor(r.path)
    } catch (e) {
      toast.error('Could not open a file picker', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      browsing = false
    }
  }
  const customEditors = $derived(editors.list?.editors.filter((e) => e.custom) ?? [])

  const editorItems = $derived.by(() => {
    const l = editors.list
    if (!l?.local) return []
    const first = l.editors.find((e) => !e.custom) ?? l.editors[0]
    return [
      { value: '', label: first ? `Automatic (${first.name})` : 'Automatic' },
      ...l.editors.map((e) => ({ value: e.id, label: e.name })),
      { value: 'none', label: 'Off' },
    ]
  })

  const urls = $derived(net?.lanEnabled ? net.urls : [])
  $effect(() => {
    const u = urls[qrFor] ?? urls[0]
    if (!u) {
      qr = ''
      return
    }
    let alive = true
    QRCode.toDataURL(u, { margin: 2, width: 220, color: { dark: '#161616', light: '#ffffff' } }).then((d) => alive && (qr = d), () => {})
    return () => (alive = false)
  })

  type Group = 'generation' | 'network' | 'storage' | 'sources' | 'editors' | 'plugins'
  const groups = $derived<{ value: Group; label: string; icon: string; find: string }[]>([
    { value: 'generation', label: 'Generation', icon: 'tune', find: 'performance gpu image tools' },
    { value: 'network', label: 'Network', icon: 'lan', find: 'lan remote devices phone' },
    { value: 'storage', label: 'Storage', icon: 'folder', find: 'folders paths disk' },
    { value: 'sources', label: 'Model sources', icon: 'cloud_download', find: 'downloads civitai hugging face' },
    ...(editors.list?.local ? [{ value: 'editors' as Group, label: 'Editors', icon: 'edit', find: 'image editor external apps' }] : []),
    { value: 'plugins', label: 'Plugins', icon: 'extension', find: 'extensions addons' },
  ])

  let scroller = $state<HTMLDivElement>()
  let body = $state<HTMLDivElement>()
  let searchEl = $state<HTMLInputElement>()
  let barH = $state(0)
  let active = $state<Group>('generation')
  // a jump holds the highlight on its target until the user scrolls by hand
  let held: Group | null = null

  const el = (g: Group) => scroller?.querySelector<HTMLElement>(`[data-group="${g}"]`)
  function jump(g: Group, smooth = true) {
    const t = el(g)
    if (!t) return
    held = g
    setActive(g)
    t.scrollIntoView({ behavior: smooth && !reducedMotion.current ? 'smooth' : 'auto', block: 'start' })
  }
  function setActive(g: Group) {
    active = g
    const h = `#/settings/${g}`
    // #/settings/<group> survives a reload and can be linked
    if (location.hash !== h && !(location.hash === '#/settings' && g === groups[0].value)) history.replaceState(history.state, '', h)
  }
  function spy() {
    const box = scroller
    if (!box || held) return
    const top = box.getBoundingClientRect().top + barH + 24
    const shown = groups.filter((g) => !el(g.value)?.hasAttribute('data-miss'))
    let cur: Group | undefined = shown[0]?.value
    if (box.scrollTop + box.clientHeight >= box.scrollHeight - 2) cur = shown.at(-1)?.value
    else for (const g of shown) if ((el(g.value)?.getBoundingClientRect().top ?? Infinity) <= top) cur = g.value
    if (cur && cur !== active) setActive(cur)
  }
  let raf = 0
  const onscroll = () => {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(spy)
  }
  $effect(() => {
    const box = scroller
    if (!box) return
    const release = () => (held = null)
    const evs = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const
    for (const e of evs) box.addEventListener(e, release, { passive: true })
    return () => evs.forEach((e) => box.removeEventListener(e, release))
  })

  const fromHash = () => location.hash.match(/^#\/settings\/(\w+)/)?.[1] as Group | undefined
  let pending = fromHash()
  $effect(() => {
    if (!pending || !s || !scroller) return
    if (groups.some((g) => g.value === pending)) {
      const g = pending
      pending = undefined
      tick().then(() => jump(g, false))
    } else if (editors.list) pending = undefined
  })
  $effect(() => {
    const on = () => {
      const g = fromHash()
      if (g && g !== active) jump(g)
    }
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  })

  let mtabs = $state<HTMLDivElement>()
  $effect(() => {
    void active
    const box = mtabs
    if (!box) return
    // keep the active section visible in the scrolling strip
    const t = box.querySelector('[aria-selected="true"]')?.getBoundingClientRect()
    const b = box.getBoundingClientRect()
    if (t) box.scrollTo({ left: box.scrollLeft + t.left - b.left - (b.width - t.width) / 2, behavior: 'smooth' })
  })

  let q = $state('')
  let found = $state<FindResult | null>(null)
  const query = $derived(q.trim())
  $effect(() => {
    const root = body
    const qq = query
    if (!root || !s) return
    const run = () => (found = qq ? applyFind(root, qq) : (applyFind(root, ''), null))
    run()
    let r = 0
    // rows come and go (lan on, editors loaded), so search again on changes
    const mo = new MutationObserver(() => {
      cancelAnimationFrame(r)
      r = requestAnimationFrame(run)
    })
    if (qq) mo.observe(root, { childList: true, subtree: true, characterData: true })
    return () => {
      mo.disconnect()
      cancelAnimationFrame(r)
    }
  })
  $effect(() => clearFind)
  let lastQuery = ''
  $effect(() => {
    const qq = query
    if (qq === lastQuery) return
    lastQuery = qq
    held = null
    if (scroller) scroller.scrollTop = 0
    tick().then(spy)
  })
  function grp(v: Group) {
    const g = groups.find((x) => x.value === v)
    return { 'data-group': v, 'data-find': g ? `${g.label} ${g.find}` : v }
  }
  const navItems = $derived(groups.map((g) => ({ ...g, disabled: !!found && !found.groups[g.value] })))

  function focusSearch() {
    searchEl?.focus()
    searchEl?.select()
  }
  function keydown(e: KeyboardEvent) {
    const t = e.target as HTMLElement
    const typing = t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName)
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'f') {
      e.preventDefault()
      focusSearch()
    } else if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault()
      focusSearch()
    }
  }


  async function copy(t: string) {
    try {
      await navigator.clipboard.writeText(t)
      toast.success('Copied')
    } catch {
      toast.error('Copy failed')
    }
  }
</script>

<svelte:window onkeydown={keydown} />

<div
  class="page"
  bind:this={scroller}
  {onscroll}
  style="--bar-h: {barH}px"
>
  <div class="head" bind:clientHeight={barH}>
    <div class="hin">
      <div class="mtabs" bind:this={mtabs}>
        <Tabs items={navItems} value={active} label="Settings sections" onchange={(g) => jump(g)} />
      </div>
      <SearchField bind:value={q} bind:input={searchEl} shortcut={mobile.current ? undefined : '/'} placeholder="Search settings" />
    </div>
  </div>
  <div class="inner" bind:this={body}>
    {#if error}
      <EmptyState icon="cloud_off" title="Could not load settings" description={error}>
        <Button icon="refresh" onclick={load}>Retry</Button>
      </EmptyState>
    {:else if !s}
      <div class="skel">
        <Skeleton height="120px" radius="var(--r-lg)" />
        <Skeleton height="180px" radius="var(--r-lg)" />
      </div>
    {:else}
      {#if readonly}
        <div class="ro">
          <span class="icon">lock</span>
          Read only
          <InfoTip text="Settings can only be changed from the machine running Somnia." />
        </div>
      {/if}

      {#if found && !found.total}
        <EmptyState icon="search_off" title="No matching settings" description={`Nothing for "${query}"`}>
          <Button icon="close" onclick={() => (q = '')}>Clear search</Button>
        </EmptyState>
      {/if}

      <div class="grp" {...grp('generation')}>
        <Card title="Generation" icon="memory">
          <div class="stack">
            <div class="line" data-find="live preview steps">
              <span class="lbl">Preview every <InfoTip text="Steps between live previews. Lower is smoother but slower." /></span>
              <div class="num">
                <NumberField
                  value={s.previewEvery}
                  min={1}
                  max={20}
                  step={1}
                  suffix="steps"
                  disabled={readonly}
                  onchange={(v) => save({ previewEvery: v })}
                />
              </div>
            </div>
            <div class="line" data-find="vram memory unload cache">
              <span class="lbl">Keep models loaded <InfoTip text="Faster next run, but holds VRAM while idle." /></span>
              <Toggle checked={s.keepModelsLoaded} disabled={readonly} aria-label="Keep models loaded" onchange={(v) => save({ keepModelsLoaded: v })} />
            </div>
            <div class="line" data-find="offload memory gpu">
              <span class="lbl">Low VRAM <InfoTip text="Offloads parts of the model to system memory. Slower, fits smaller GPUs." /></span>
              <Toggle checked={s.lowVram} disabled={readonly} aria-label="Low VRAM" onchange={(v) => save({ lowVram: v })} />
            </div>
            <div class="line" data-find="tf32 fp16 speed rtx cuda">
              <span class="lbl">NVIDIA optimizations <InfoTip text="TF32 and fp16 accumulation matmuls, fp16 Anima. Faster on RTX cards, tiny numeric differences." /></span>
              <Toggle
                checked={s.nvidiaOptimizations}
                disabled={readonly}
                aria-label="NVIDIA optimizations"
                onchange={(v) => save({ nvidiaOptimizations: v })}
              />
            </div>
          </div>
        </Card>

        <Card title="Image tools" icon="background_replace">
          <div class="stack">
            <div class="line" data-find="remove bg transparent cutout birefnet">
              <span class="lbl">Background removal <InfoTip text="ToonOut is BiRefNet fine-tuned on anime, cleanest edges and hair gaps (500 MB download on first use). ISNet is smaller and faster but leaks background between strands." /></span>
              <div class="pick">
                <Select
                  size="sm"
                  items={[
                    { value: 'toonout', label: 'ToonOut' },
                    { value: 'isnet', label: 'ISNet' },
                  ]}
                  value={s.bgModel}
                  disabled={readonly}
                  onchange={(v: string) => save({ bgModel: v })}
                />
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div class="grp" {...grp('network')}>
        <Card title="Network" icon="lan">
          <div class="stack">
            <div class="line" data-find="lan wifi phone remote share expose">
              <span class="lbl">Local network access <InfoTip text="Lets phones and other computers on your network open Somnia. Turn off when not needed." /></span>
              <Toggle checked={s.lanEnabled} disabled={readonly} aria-label="Local network access" onchange={(v) => save({ lanEnabled: v })} />
            </div>
            {#if s.lanEnabled}
              {#if urls.length}
                <div class="lan" data-find="local network access lan address url qr phone">
                  <div class="urls">
                    {#each urls as u, i}
                      <div class="url" class:sel={i === qrFor}>
                        <button type="button" class="ub" onclick={() => (qrFor = i)}>{u}</button>
                        <IconButton icon="content_copy" label="Copy" size="sm" onclick={() => copy(u)} />
                      </div>
                    {/each}
                  </div>
                  {#if qr}<img class="qr" src={qr} alt="QR code for {urls[qrFor] ?? urls[0]}" width="150" height="150" />{/if}
                </div>
              {:else}
                <div class="muted" data-find="local network access lan address">No network addresses found</div>
              {/if}
              <LanSecurity settings={s} {readonly} {local} {save} />
            {/if}
          </div>
        </Card>

        <NotificationsCard />
      </div>

      <div class="grp" {...grp('storage')}>
        <Card title="Storage" icon="folder">
          <div class="stack">
            <Field label="Model folders" info="Folders scanned for checkpoints, LoRAs, VAEs and so on.">
              {#snippet children()}
                <div class="roots">
                  {#each s!.modelRoots as r, i (r + i)}
                    <div class="root">
                      <TextInput mono value={r} disabled={readonly} onchange={(v) => setRoot(i, v)} />
                      <IconButton icon="close" label="Remove" size="sm" disabled={readonly} onclick={() => removeRoot(i)} />
                    </div>
                  {/each}
                  <div class="root">
                    <TextInput mono bind:value={newRoot} placeholder="Add folder" disabled={readonly} onenter={addRoot} />
                    <IconButton icon="add" label="Add" size="sm" disabled={readonly || !newRoot.trim()} onclick={addRoot} />
                  </div>
                </div>
              {/snippet}
            </Field>
            <Field label="Download folder" info="Where Civitai downloads are saved.">
              {#snippet children(id)}
                <TextInput {id} mono value={s!.downloadRoot} disabled={readonly} onchange={(v) => save({ downloadRoot: v })} />
              {/snippet}
            </Field>
            <Field label="Output folder" info="Where generated images are written.">
              {#snippet children(id)}
                <TextInput {id} mono value={s!.outputDir} disabled={readonly} onchange={(v) => save({ outputDir: v })} />
              {/snippet}
            </Field>
          </div>
        </Card>
      </div>

      <div class="grp" {...grp('sources')}>
        <Card title="Civitai" icon="cloud_download">
          <div class="stack">
            <Field label="API token" info="Most downloads need one. Create it in your Civitai account settings.">
              {#snippet children(id)}
                <TextInput {id} type="password" autocomplete="off" bind:value={token} disabled={readonly} onchange={saveToken} />
              {/snippet}
            </Field>
            <div class="line" data-find="adult explicit">
              <span class="lbl">Show NSFW <InfoTip text="Include adult content when browsing Civitai." /></span>
              <Toggle checked={s.showNsfw} disabled={readonly} aria-label="Show NSFW" onchange={(v) => save({ showNsfw: v })} />
            </div>
            <div class="line" data-find="hash updates versions">
              <span class="lbl">Identify models <InfoTip text="Hash new local models in the background to find them on Civitai (names, trigger words), and check daily for newer versions." /></span>
              <Toggle checked={s.autoIdentify} disabled={readonly} aria-label="Identify models" onchange={(v) => save({ autoIdentify: v })} />
            </div>
          </div>
        </Card>

        <Card title="Hugging Face" icon="hub">
          <div class="stack">
            <Field label="Access token" info="Only needed for gated repos. Create a read token in your Hugging Face account settings and accept the repo license there.">
              {#snippet children(id)}
                <TextInput {id} type="password" autocomplete="off" bind:value={hfToken} disabled={readonly} onchange={saveHfToken} />
              {/snippet}
            </Field>
          </div>
        </Card>
      </div>

      {#if editors.list?.local}
        <div class="grp" {...grp('editors')}>
          <Card title="Image editor" icon="edit">
            <div class="stack">
              {#if editors.list.editors.length}
                <Field label="Open images in" info="Adds an open button wherever you view an image. Only shown on this machine.">
                  {#snippet children(id)}
                    <div class="root">
                      <Select
                        {id}
                        items={editorItems}
                        value={s!.imageEditor}
                        disabled={readonly}
                        onchange={(v: string) => save({ imageEditor: v })}
                        style="flex: 1; min-width: 0"
                      >
                        {#snippet item(it)}
                          <span class="ed">
                            {#if it.value && it.value !== 'none'}
                              <img src={api.editorIconUrl(it.value)} alt="" width="18" height="18" />
                            {:else}
                              <span class="icon">{it.value === 'none' ? 'block' : 'auto_awesome'}</span>
                            {/if}
                            {it.label}
                          </span>
                        {/snippet}
                      </Select>
                      <IconButton icon="refresh" label="Scan again" size="sm" onclick={() => editors.load(true)} />
                    </div>
                  {/snippet}
                </Field>
              {:else}
                <div class="line">
                  <span class="muted">No Photoshop, Krita or Paint.NET found</span>
                  <Button size="sm" icon="refresh" onclick={() => editors.load(true)}>Scan again</Button>
                </div>
              {/if}
              <Field label="Other editors" info="Add any program that opens image files. Pick its .exe, or paste its path.">
                {#snippet children()}
                  <div class="roots">
                    {#each customEditors as e (e.id)}
                      <div class="root cust">
                        <img src={api.editorIconUrl(e.id)} alt="" width="18" height="18" onerror={(ev) => ((ev.currentTarget as HTMLImageElement).style.visibility = 'hidden')} />
                        <TextInput value={e.name} disabled={readonly} onchange={(v) => v.trim() && editorCall(editors.apply(api.renameEditor(e.id, v.trim())))} />
                        <span class="cpath" title={e.path ?? ''}>{e.path}</span>
                        <IconButton icon="close" label="Remove" size="sm" disabled={readonly} onclick={() => editorCall(editors.apply(api.removeEditor(e.id)))} />
                      </div>
                    {/each}
                    <div class="root">
                      <TextInput mono bind:value={newEditor} placeholder="Path to a program" disabled={readonly} onenter={() => addEditor()} />
                      {#if newEditor.trim()}
                        <IconButton icon="add" label="Add" size="sm" disabled={readonly} onclick={() => addEditor()} />
                      {:else}
                        <Button size="sm" icon="folder_open" loading={browsing} disabled={readonly} onclick={browseEditor}>Browse</Button>
                      {/if}
                    </div>
                  </div>
                {/snippet}
              </Field>
            </div>
          </Card>
        </div>
      {/if}

      <div class="grp" {...grp('plugins')}>
        <PluginsCard {readonly} />
      </div>
    {/if}
    <div class="about"><Logo size={22} wordmark /></div>
  </div>
</div>

<style>
  .page {
    height: 100%;
    min-height: 0;
    overflow-y: auto;
  }
  .head {
    position: sticky;
    top: 0;
    z-index: 2;
    background: color-mix(in srgb, var(--bg) 88%, transparent);
    backdrop-filter: blur(12px);
  }
  .hin,
  .inner {
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    padding: 0 var(--sp-4);
  }
  .hin {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding-top: var(--sp-4);
    padding-bottom: var(--sp-3);
  }
  .mtabs {
    margin: 0 calc(-1 * var(--sp-4));
    padding: 0 var(--sp-4);
    overflow-x: auto;
    scrollbar-width: none;
  }
  .mtabs :global(.tabs) {
    width: max-content;
    min-width: 100%;
  }
  .inner {
    display: flex;
    flex-direction: column;
    gap: var(--sp-5);
    padding-top: var(--sp-2);
    padding-bottom: var(--sp-6);
  }
  .grp {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
    scroll-margin-top: calc(var(--bar-h, 0px) + var(--sp-3));
  }
  .inner :global([data-miss]) {
    display: none !important;
  }
  .inner :global([data-hit]) {
    color: var(--warning);
  }
  :global(::highlight(settings-find)) {
    background-color: var(--warning-soft);
    color: var(--warning);
  }
  .about {
    display: flex;
    justify-content: center;
    padding: var(--sp-4) 0 0;
  }
  .about :global(.logo) {
    color: var(--text-faint);
  }
  .pick {
    width: 150px;
  }
  .skel,
  .stack {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
  }
  .ro {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--warning-soft);
    color: var(--warning);
    font-size: var(--fs-sm);
  }
  .ro .icon {
    font-size: 18px;
  }
  .line {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-3);
    min-height: 34px;
  }
  .lbl {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .num {
    width: 150px;
  }
  .roots {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .root {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .lan {
    display: flex;
    gap: var(--sp-4);
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .urls {
    flex: 1;
    min-width: 200px;
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
  }
  .url {
    display: flex;
    align-items: center;
    border-radius: var(--r-md);
    padding-left: var(--sp-2);
  }
  .url.sel {
    background: var(--surface-3);
  }
  .ub {
    flex: 1;
    min-width: 0;
    text-align: left;
    border: 0;
    background: none;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--fs-sm);
    padding: 6px 0;
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .qr {
    border-radius: var(--r-md);
    border: 1px solid var(--hairline);
    background: var(--accent-strong);
  }
  .muted {
    color: var(--text-muted);
    font-size: var(--fs-sm);
  }
  .ed {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .ed img {
    width: 18px;
    height: 18px;
    object-fit: contain;
  }
  .ed .icon {
    font-size: 18px;
    width: 18px;
    color: var(--text-muted);
  }
  .cust img {
    flex: none;
    width: 18px;
    height: 18px;
    object-fit: contain;
  }
  .cust :global(input) {
    max-width: 180px;
  }
  .cpath {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    direction: rtl;
    text-align: left;
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--fs-xs);
  }
</style>
