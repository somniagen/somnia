import { api } from '$lib/api'
import { studio } from '$features/inpaint/studio.svelte'
import { live } from '$lib/live.svelte'
import { session } from '$lib/session.svelte'
import type { GalleryItem, InitImage } from '$lib/types'
import { toast } from '$lib/ui'

class Actions {
  deleted = $state<Set<string>>(new Set())
}
export const actions = new Actions()

export const uploadUrl = (id: string) => `/files/uploads/${id}.png`

export function go(hash: string) {
  if (location.hash !== hash) location.hash = hash
}

function ensureUpload(item: GalleryItem) {
  return api.galleryUpload(item.id)
}

export function newInit(imageId: string, patch: Partial<InitImage> = {}): InitImage {
  return { imageId, denoise: 0.6, maskId: null, maskBlur: 4, padding: 32, onlyMasked: false, fill: 'original', ...patch }
}

export function reuse(item: GalleryItem) {
  if (!item.params) return toast.info('No params stored in this image')
  const { init: _init, stackId: _s, ...rest } = item.params
  session.applyParams({ ...rest, seed: item.seed })
  go('#/')
  toast.success('Params restored')
}

async function guard(fn: () => Promise<void>) {
  try {
    await fn()
  } catch (e) {
    toast.error('Failed', { description: e instanceof Error ? e.message : String(e) })
  }
}

export function img2img(item: GalleryItem) {
  return guard(async () => {
    const up = await ensureUpload(item)
    session.update({ init: newInit(up.id) })
    go('#/')
    toast.success('Image set as input')
  })
}

export function upscaleAgain(item: GalleryItem) {
  return guard(async () => {
    const up = await ensureUpload(item)
    session.update({
      init: newInit(up.id, { denoise: 0.3 }),
      upscale: { ...(session.params?.upscale ?? { upscaler: '', scale: 2 }), enabled: true },
      width: item.width,
      height: item.height,
    })
    go('#/')
    toast.success('Ready to upscale', { description: 'Low denoise input with final upscale on' })
  })
}

export function openInpaint(item: GalleryItem) {
  go('#/inpaint')
  return guard(() => studio.open(item))
}

export function download(item: GalleryItem) {
  const a = document.createElement('a')
  a.href = item.url
  a.download = item.url.split('/').pop() ?? 'image.png'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export async function removeImage(item: GalleryItem): Promise<boolean> {
  try {
    await api.deleteImage(item.id)
  } catch (e) {
    toast.error('Delete failed', { description: e instanceof Error ? e.message : String(e) })
    return false
  }
  actions.deleted = new Set([...actions.deleted, item.id])
  live.recent = live.recent.filter((i) => i.id !== item.id)
  return true
}

export async function addFile(file: File) {
  try {
    const up = await api.upload(file, file.name)
    if (up.params) {
      const params = up.params
      toast.info('Image has params', {
        action: {
          label: 'Reuse params',
          run: () => {
            const { init: _i, ...rest } = params
            session.applyParams(rest)
          },
        },
        duration: 10000,
      })
      return
    }
    session.update({ init: newInit(up.id) })
    toast.success('Image set as input')
  } catch (e) {
    toast.error('Upload failed', { description: e instanceof Error ? e.message : String(e) })
  }
}
