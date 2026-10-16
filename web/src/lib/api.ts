import type {
  CivitaiImage,
  CivitaiModel,
  CivitaiSearchQuery,
  CivitaiSearchResult,
  Detection,
  Download,
  EditorList,
  GalleryItem,
  GenParams,
  Job,
  LocalModel,
  ModelKind,
  NetInfo,
  RelatedTag,
  Presets,
  SavedPrompt,
  Settings,
  Snapshot,
  Tag,
  TagCategory,
  TagWiki,
  UploadResult,
} from './types'

export interface GalleryFilter {
  // comma separated terms matched against prompt, model, loras, editor and seed; "-term" excludes
  q?: string
  model?: string
  sort?: 'newest' | 'oldest' | 'model'
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function req<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const init: RequestInit = { method, signal }
  if (body instanceof FormData) init.body = body
  else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'content-type': 'application/json' }
  }
  const res = await fetch(path, init)
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = j.detail ?? j.message ?? msg
    } catch {}
    throw new ApiError(res.status, typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') ?? ''
  return (ct.includes('json') ? res.json() : res.text()) as Promise<T>
}

function qs(o: object): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

const get = <T>(p: string, signal?: AbortSignal) => req<T>('GET', p, undefined, signal)
const post = <T>(p: string, b?: unknown) => req<T>('POST', p, b)
const put = <T>(p: string, b?: unknown) => req<T>('PUT', p, b)
const patch = <T>(p: string, b?: unknown) => req<T>('PATCH', p, b)
const del = <T>(p: string) => req<T>('DELETE', p)

export const api = {
  state: () => get<Snapshot>('/api/state'),
  presets: () => get<Presets>('/api/presets'),
  queue: (params: GenParams, count = 1) => post<{ ids: string[] }>('/api/jobs', { params, count }),
  cancel: (id: string) => del<void>(`/api/jobs/${id}`),
  reorder: (ids: string[]) => post<Job[]>('/api/jobs/reorder', { ids }),
  clearQueue: () => post<void>('/api/jobs/clear'),

  gallery: (cursor?: string, limit = 60, filter: GalleryFilter = {}) =>
    get<{ items: GalleryItem[]; nextCursor: string | null }>(`/api/gallery${qs({ cursor, limit, ...filter })}`),
  galleryModels: () => get<{ id: string; count: number }[]>('/api/gallery/models'),
  galleryUpload: (id: string) => post<UploadResult>(`/api/gallery/${id}/upload`),
  stack: (id: string) => get<GalleryItem[]>(`/api/gallery/${id}/stack`),
  deleteImage: (id: string) => del<void>(`/api/gallery/${id}`),
  upload: (file: Blob, name = 'image.png') => {
    const fd = new FormData()
    fd.append('file', file, name)
    return post<UploadResult>('/api/upload', fd)
  },

  settings: () => get<Settings>('/api/settings'),
  updateSettings: (s: Partial<Settings>) => patch<Settings>('/api/settings', s),
  net: () => get<NetInfo>('/api/net'),

  prompts: () => get<SavedPrompt[]>('/api/prompts'),
  createPrompt: (p: Omit<SavedPrompt, 'id' | 'createdAt' | 'updatedAt'>) => post<SavedPrompt>('/api/prompts', p),
  updatePrompt: (p: SavedPrompt) => put<SavedPrompt>(`/api/prompts/${p.id}`, p),
  deletePrompt: (id: string) => del<void>(`/api/prompts/${id}`),

  models: (kind?: ModelKind) => get<LocalModel[]>(`/api/models${qs({ kind })}`),
  rescan: () => post<LocalModel[]>('/api/models/rescan'),
  deleteModel: (id: string) => del<void>(`/api/models/${encodeURIComponent(id)}`),
  modelPreviewUrl: (id: string) => `/api/models/preview/${encodeURIComponent(id)}`,

  civitaiSearch: (q: CivitaiSearchQuery, signal?: AbortSignal) =>
    get<CivitaiSearchResult>(`/api/civitai/search${qs(q)}`, signal),
  civitaiModel: (id: number) => get<CivitaiModel>(`/api/civitai/models/${id}`),
  civitaiImages: (modelVersionId: number, cursor?: string, limit = 30) =>
    get<{ items: CivitaiImage[]; nextCursor: string | null }>(`/api/civitai/images${qs({ modelVersionId, cursor, limit })}`),
  download: (versionId: number, fileId?: number) => post<Download>('/api/civitai/download', { versionId, fileId }),
  downloads: () => get<Download[]>('/api/downloads'),
  cancelDownload: (id: string) => del<void>(`/api/downloads/${id}`),

  tags: (q: string, limit = 20, signal?: AbortSignal) => get<Tag[]>(`/api/tags/search${qs({ q, limit })}`, signal),
  tagRelated: (name: string, limit = 16) => get<RelatedTag[]>(`/api/tags/related/${encodeURIComponent(name)}${qs({ limit })}`),
  tagWiki: (name: string) => get<TagWiki>(`/api/tags/wiki/${encodeURIComponent(name)}`),
  tagLookup: (names: string[]) =>
    get<Record<string, TagCategory>>(`/api/tags/lookup${qs({ names: names.join(',') })}`),

  editors: (rescan = false) => get<EditorList>(`/api/editors${qs({ rescan: rescan || undefined })}`),
  editorIconUrl: (id: string) => `/api/editors/${encodeURIComponent(id)}/icon`,
  browseEditor: () => post<{ path: string | null; name: string | null }>('/api/editors/browse'),
  addEditor: (path: string, name?: string) => post<EditorList>('/api/editors/custom', { path, name }),
  renameEditor: (id: string, name: string) => put<EditorList>(`/api/editors/custom/${encodeURIComponent(id)}`, { name }),
  removeEditor: (id: string) => del<EditorList>(`/api/editors/custom/${encodeURIComponent(id)}`),
  openInEditor: (url: string, editor?: string, galleryId?: string) =>
    post<{ editor: string; session: string }>('/api/editors/open', { url, editor, galleryId }),

  detect: (imageId: string, detector: string, confidence = 0.3) =>
    post<Detection[]>('/api/detect', { imageId, detector, confidence }),
}
