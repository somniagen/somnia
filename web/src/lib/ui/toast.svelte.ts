export type ToastKind = 'success' | 'error' | 'info'

export interface ToastOptions {
  description?: string
  duration?: number
  action?: { label: string; run: () => void }
  icon?: string
}

export interface ToastItem extends ToastOptions {
  id: number
  kind: ToastKind
  message: string
}

let next = 0
export const toasts = $state<ToastItem[]>([])
const timers = new Map<number, ReturnType<typeof setTimeout>>()

function push(kind: ToastKind, message: string, o: ToastOptions = {}) {
  const id = ++next
  toasts.push({ id, kind, message, ...o })
  if (toasts.length > 5) dismiss(toasts[0].id)
  arm(id, o.duration ?? (kind === 'error' ? 7000 : 4000))
  return id
}

function arm(id: number, ms: number) {
  clearTimeout(timers.get(id))
  if (ms > 0 && Number.isFinite(ms)) timers.set(id, setTimeout(() => dismiss(id), ms))
}

export function dismiss(id: number) {
  clearTimeout(timers.get(id))
  timers.delete(id)
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

export function pause(id: number) {
  clearTimeout(timers.get(id))
}

export function resume(id: number) {
  arm(id, 2500)
}

export const toast = Object.assign((message: string, o?: ToastOptions) => push('info', message, o), {
  success: (message: string, o?: ToastOptions) => push('success', message, o),
  error: (message: string, o?: ToastOptions) => push('error', message, o),
  info: (message: string, o?: ToastOptions) => push('info', message, o),
  dismiss,
})
