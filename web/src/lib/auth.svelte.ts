import type { AuthStatus } from './types'

class Auth {
  // true when the server wants a lan password from this device
  locked = $state(false)

  async check(): Promise<boolean> {
    try {
      const r = await fetch('/api/auth')
      if (r.ok) {
        const s = (await r.json()) as AuthStatus
        this.locked = s.required && !s.ok
      }
    } catch {}
    return !this.locked
  }

  lock() {
    this.locked = true
  }

  async login(password: string): Promise<boolean> {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    if (r.status === 401) return false
    if (!r.ok) throw new Error(r.statusText || `HTTP ${r.status}`)
    // simplest way to reload every view, socket and cache with the new cookie
    location.reload()
    return true
  }

  async logout() {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
    location.reload()
  }
}

export const auth = new Auth()
