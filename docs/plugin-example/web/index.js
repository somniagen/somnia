export default function activate(host) {
  const { ui } = host

  host.addPage({
    id: 'main',
    title: 'Hello',
    icon: 'waving_hand',
    mount(el) {
      el.innerHTML = '<div class="hello"><h2>Hello from a plugin</h2><p class="n"></p><div class="b"></div></div>'
      const n = el.querySelector('.n')
      const show = (s) => (n.textContent = `${s.finished} jobs finished since install`)
      host.json('/stats').then(show)
      const off = host.on('finished', show)
      const btn = ui.mount(ui.Button, {
        target: el.querySelector('.b'),
        props: {
          icon: 'send',
          onclick: async () => ui.toast.info(JSON.stringify(await host.json('/echo', { method: 'POST', body: { hi: 1 } }))),
          children: ui.createRawSnippet(() => ({ render: () => '<span>Echo</span>' })),
        },
      })
      return () => {
        off()
        ui.unmount(btn)
      }
    },
  })

  host.addImageAction({
    id: 'seed',
    label: 'Copy seed',
    icon: 'tag',
    run: async (item) => {
      await navigator.clipboard.writeText(String(item.params?.seed ?? ''))
      host.toast.success('Seed copied')
    },
  })

  host.addStyle('.hello { padding: var(--sp-5); } .hello .n { color: var(--text-muted); }')
}
