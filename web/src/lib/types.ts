export type Family = 'illustrious' | 'anima'

export type ModelKind = 'checkpoint' | 'lora' | 'vae' | 'text_encoder' | 'upscaler' | 'detector'

export interface LoraRef {
  id: string
  weight: number
}

export interface SecondPass {
  enabled: boolean
  upscaler: string
  scale: number
  steps: number
  denoise: number
  cfg: number | null
  sampler: string | null
  scheduler: string | null
  model: string | null
}

export interface DetailerPass {
  enabled: boolean
  detector: string
  prompt: string
  negative: string
  confidence: number
  dilate: number
  blur: number
  denoise: number
  steps: number
  padding: number
  // prompt is appended to the main prompt instead of replacing it
  appendPrompt?: boolean
}

export interface FinalUpscale {
  enabled: boolean
  upscaler: string
  scale: number
}

export interface InitImage {
  imageId: string
  denoise: number
  maskId: string | null
  maskBlur: number
  padding: number
  onlyMasked: boolean
  fill: 'original' | 'noise' | 'blur'
}

export interface GenParams {
  family: Family
  model: string
  vae: string | null
  textEncoder: string | null
  prompt: string
  negative: string
  width: number
  height: number
  steps: number
  cfg: number
  sampler: string
  scheduler: string
  seed: number
  clipSkip: number
  batchSize: number
  loras: LoraRef[]
  pag: { enabled: boolean; scale: number }
  cfgRescale: number
  secondPass: SecondPass
  detailers: DetailerPass[]
  upscale: FinalUpscale
  init: InitImage | null
  // gallery stack root the result is filed under (inpaint results), stripped from saved params
  stackId?: string | null
  // the editor segments behind prompt/negative, so reusing an image restores its boilerplate
  segments?: { positive: PromptSegment[]; negative: PromptSegment[] } | null
}

export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled'

export interface Job {
  id: string
  params: GenParams
  status: JobStatus
  createdAt: number
  startedAt: number | null
  finishedAt: number | null
  images: GalleryItem[]
  error: string | null
}

export type Phase = 'load' | 'encode' | 'sample' | 'second' | 'detail' | 'upscale' | 'decode' | 'save'

export interface Progress {
  jobId: string
  phase: Phase
  step: number
  total: number
  overall: number
  etaSec: number | null
  preview: string | null
  label?: string | null
}

export interface GalleryItem {
  id: string
  url: string
  thumbUrl: string
  width: number
  height: number
  seed: number
  createdAt: number
  params: GenParams | null
  stackId?: string | null
  // saved back from an external editor; sourceId is the image it was opened from
  editedWith?: { id: string; name: string } | null
  sourceId?: string | null
  updatedAt?: number
  // only on /api/gallery roots
  stackCount?: number
  stackCover?: string | null
}

export interface LocalModel {
  id: string
  kind: ModelKind
  family: Family | null
  name: string
  path: string
  size: number
  mtime: number
  previewUrl: string | null
  civitai: CivitaiLocalInfo | null
}

export interface CivitaiLocalInfo {
  modelId: number
  versionId: number
  name: string
  versionName: string
  baseModel: string
  trainedWords: string[]
  nsfw: boolean
}

export interface CivitaiFile {
  id: number
  name: string
  sizeKB: number
  type: string
  primary: boolean
  format: string | null
  fp: string | null
}

export interface CivitaiImage {
  id: number
  url: string
  width: number
  height: number
  nsfwLevel: number
  type: 'image' | 'video'
  meta: {
    prompt?: string
    negativePrompt?: string
    sampler?: string
    cfgScale?: number
    steps?: number
    seed?: number
    Size?: string
    [k: string]: unknown
  } | null
}

export interface CivitaiVersion {
  id: number
  name: string
  baseModel: string
  createdAt: string
  trainedWords: string[]
  files: CivitaiFile[]
  images: CivitaiImage[]
  downloadCount: number
  description: string | null
  installed: string | null
}

export interface CivitaiModel {
  id: number
  name: string
  type: string
  nsfw: boolean
  creator: { username: string; image: string | null } | null
  tags: string[]
  description: string | null
  stats: { downloadCount: number; thumbsUpCount: number; favoriteCount?: number; commentCount?: number }
  versions: CivitaiVersion[]
}

export interface CivitaiSearchQuery {
  query?: string
  types?: string
  sort?: 'Highest Rated' | 'Most Downloaded' | 'Newest'
  period?: 'AllTime' | 'Year' | 'Month' | 'Week' | 'Day'
  baseModels?: string
  nsfw?: boolean
  cursor?: string
  limit?: number
}

export interface CivitaiSearchResult {
  items: CivitaiModel[]
  nextCursor: string | null
}

export type DownloadStatus = 'queued' | 'downloading' | 'done' | 'error' | 'cancelled'

export interface Download {
  id: string
  name: string
  kind: ModelKind
  modelId: number
  versionId: number
  received: number
  total: number
  speed: number
  status: DownloadStatus
  error: string | null
}

export type TagCategory = 0 | 1 | 3 | 4 | 5

export interface Tag {
  name: string
  category: TagCategory
  count: number
  aliases: string[]
  matchedAlias: string | null
}

export interface RelatedTag {
  name: string
  category: TagCategory | null
  count: number
}

export interface TagWiki {
  name: string
  category: TagCategory | null
  body: string
  otherNames: string[]
  url: string
}

export interface PromptSegment {
  text: string
  locked: boolean
  // boilerplate color key (see features/prompt/segcolor.ts), auto by content when missing
  color?: string
}

export interface SavedPrompt {
  id: string
  name: string
  family: Family | null
  positive: PromptSegment[]
  negative: PromptSegment[]
  createdAt: number
  updatedAt: number
}

export interface Detection {
  label: string
  confidence: number
  bbox: [number, number, number, number]
  maskUrl: string | null
}

export interface UploadResult {
  id: string
  url: string
  width: number
  height: number
  params: GenParams | null
}

export interface Settings {
  lanEnabled: boolean
  port: number
  modelRoots: string[]
  downloadRoot: string
  outputDir: string
  civitaiToken: string
  showNsfw: boolean
  previewEvery: number
  keepModelsLoaded: boolean
  lowVram: boolean
  nvidiaOptimizations: boolean
  imageEditor: string
  customEditors: { name: string; path: string }[]
}

export interface ImageEditor {
  id: string
  name: string
  // added by hand in settings; path is only sent for these
  custom?: boolean
  path?: string | null
}

export interface EditorList {
  // false when the ui is opened from another device, editors only launch on the server machine
  local: boolean
  editors: ImageEditor[]
  current: string | null
}

export interface NetInfo {
  lanEnabled: boolean
  urls: string[]
}

export interface FamilyInfo {
  family: Family
  defaults: GenParams
  samplers: string[]
  schedulers: string[]
  resolutions: [number, number][]
}

export interface Presets {
  families: Record<Family, FamilyInfo>
}

export interface Snapshot {
  queue: Job[]
  current: Progress | null
  recent: GalleryItem[]
  downloads: Download[]
}

export type WsMessage =
  | ({ type: 'snapshot' } & Snapshot)
  | { type: 'queue'; queue: Job[] }
  | ({ type: 'progress' } & Progress)
  | { type: 'done'; job: Job }
  | { type: 'error'; jobId: string; message: string }
  | { type: 'download'; download: Download }
  | { type: 'models_changed' }
  | { type: 'settings'; settings: Settings }
  // created or re-saved outside a job (external editor saves)
  | { type: 'gallery_item'; item: GalleryItem }
