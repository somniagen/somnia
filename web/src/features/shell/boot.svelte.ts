import { auth } from '$lib/auth.svelte'
import { live } from '$lib/live.svelte'
import { session } from '$lib/session.svelte'

class Boot {
  state = $state<'idle' | 'loading' | 'ready' | 'error'>('idle')
  error = $state('')
  private started = false

  start() {
    if (this.started || auth.locked) return
    this.started = true
    live.start()
    this.load()
  }

  async load() {
    this.state = 'loading'
    this.error = ''
    try {
      await session.init()
      this.state = 'ready'
    } catch (e) {
      // the login screen takes over, a reload follows a successful login
      if (auth.locked) return
      this.error = e instanceof Error ? e.message : String(e)
      this.state = 'error'
    }
  }
}

export const boot = new Boot()
