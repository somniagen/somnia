import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import 'material-symbols/rounded.css'
import './lib/ui/tokens.css'
import { mount } from 'svelte'
import App from './App.svelte'
import AuthGate from './features/shell/AuthGate.svelte'
import { auth } from './lib/auth.svelte'

if ('serviceWorker' in navigator && isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {})

const gate = document.createElement('div')
document.body.append(gate)

// lan clients with a password set see only the login screen until they unlock
auth.check().then(() => {
  if (!auth.locked) mount(App, { target: document.getElementById('app')! })
  mount(AuthGate, { target: gate })
})
