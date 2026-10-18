export type Family = 'illustrious' | 'anima'

export type ModelKind = 'checkpoint' | 'lora' | 'vae' | 'text_encoder' | 'upscaler' | 'detector' | 'embedding'

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

export interface TiledRefine {
  enabled: boolean
  denoise: number
  steps: number
  tileSize: number
  padding: number
}

export interface FinalUpscale {
  enabled: boolean
  upscaler: string
  scale: number
  // img2img refine of the upscaled image tile by tile
  tiled?: TiledRefine | null
}

export interface Variation {
  enabled: boolean
  // -1 = random per job
  seed: number
  strength: number
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
  // variation seed: the base noise is blended toward noise from variation.seed
  variation?: Variation | null
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
  // queues a copy of itself when it finishes, until cancelled
  repeat?: boolean
  // set on jobs queued by an x/y/z grid
  grid?: { id: string; x: number; y: number; z: number } | null
}

export interface GridAxisValue {
  label: string
  // deep merged into the base params; "$sr": [search, replace] edits the prompts, "$lora": { id, weight } sets one lora
  patch: Record<string, unknown>
}

export interface GridAxis {
  kind: string
  label: string
  values: GridAxisValue[]
}

export type GridStatus = 'running' | 'composing' | 'done' | 'failed'

export interface GridCell {
  x: number
  y: number
  z: number
  jobId: string | null
  // stays queued while the job runs; compare jobId with the running job
  status: 'queued' | 'done' | 'error' | 'cancelled'
  item: GalleryItem | null
  error: string | null
}

export interface Grid {
  id: string
  createdAt: number
  finishedAt: number | null
  status: GridStatus
  base: GenParams
  // x, then optional y and z
  axes: GridAxis[]
  // z-major, then rows (y), then columns (x)
  cells: GridCell[]
  // composed image per z value (stack roots), filled once every cell finished
  images: GalleryItem[]
}

export type Phase = 'load' | 'encode' | 'sample' | 'second' | 'detail' | 'upscale' | 'refine' | 'decode' | 'save'

export interface Progress {
  jobId: string
  phase: Phase
  step: number
  total: number
  overall: number
  etaSec: number | null
  preview: string | null
  label?: string | null
  // area being rendered (detailer, tiled refine), fractions of the whole image
  region?: Region | null
}

export interface Region {
  x: number
  y: number
  w: number
  h: number
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
  stackCoverId?: string | null
  stackCoverAlpha?: boolean
  // the whole cover item, shown for the stack in tiles and the lightbox
  stackCoverItem?: GalleryItem | null
  // chosen stack cover, only on roots
  coverId?: string | null
  // composed x/y/z grid image
  grid?: { id: string; z: number } | null
  favorite?: boolean
  albums?: string[]
  // has transparency (background removed)
  alpha?: boolean
}

export interface GalleryAlbum {
  name: string
  count: number
  cover: string | null
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
  // newer civitai version with the same base model, not installed (background update check)
  updateVersionId?: number | null
  updateVersionName?: string | null
}

// per-model defaults stored on the server; checkpoints keep sampling params, loras a weight
export type ModelDefaultParams = Partial<
  Pick<GenParams, 'steps' | 'cfg' | 'sampler' | 'scheduler' | 'clipSkip' | 'cfgRescale' | 'pag' | 'vae' | 'width' | 'height'>
>

export interface ModelDefaults {
  params?: ModelDefaultParams
  weight?: number
  updatedAt: number
}

export interface IdentifyState {
  running: boolean
  done: number
  total: number
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

export type HfCategory = '' | 'checkpoint' | 'lora' | 'vae' | 'text_encoder' | 'upscaler' | 'bbox' | 'segm' | 'embedding'

export interface HfSearchQuery {
  query?: string
  category?: HfCategory
  sort?: 'downloads' | 'likes' | 'trendingScore' | 'lastModified'
  cursor?: string
  limit?: number
}

export interface HfRepo {
  id: string
  author: string
  downloads: number
  likes: number
  lastModified: string | null
  gated: boolean
  tags: string[]
  // detected file kinds, detectors as 'bbox' / 'segm'
  kinds: string[]
  // files matching the searched category
  files: number
}

export interface HfFile {
  path: string
  size: number
  // null when the file type was not recognized
  kind: ModelKind | null
  sub: 'bbox' | 'segm' | null
  installed: boolean | null
}

export interface HfRepoDetail extends Omit<HfRepo, 'kinds' | 'files'> {
  sha: string | null
  readme: string
  files: HfFile[]
}

export interface HfSearchResult {
  items: HfRepo[]
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
  source?: 'civitai' | 'hf'
  // hugging face repo id and file path
  repo?: string
  file?: string
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
  // structured anima prompt section, unset means the plain prompt
  section?: PromptSection
}

export type PromptSection = 'quality' | 'subject' | 'artists' | 'prompt'

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
  // "****" when a password is set, "" when not; patch a plain value to set, "" to clear
  lanPassword: string
  // tls cert and key paths, https is used after a restart when both exist
  httpsCert: string
  httpsKey: string
  port: number
  modelRoots: string[]
  downloadRoot: string
  outputDir: string
  civitaiToken: string
  hfToken: string
  showNsfw: boolean
  autoIdentify: boolean
  previewEvery: number
  keepModelsLoaded: boolean
  lowVram: boolean
  nvidiaOptimizations: boolean
  // background removal model: 'toonout' (birefnet anime) or 'isnet'
  bgModel: string
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

export interface AuthStatus {
  // a lan password is set and this client is not on the server machine
  required: boolean
  ok: boolean
}

export interface PushSubscriptionJson {
  endpoint: string
  keys: { p256dh: string; auth: string }
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

export interface PluginInfo {
  id: string
  name: string
  version: string
  description: string
  enabled: boolean
  loaded: boolean
  error: string | null
  // has a plugin.py
  backend: boolean
  // web entry file name, served from /api/plugins/{id}/web/
  web: string | null
  // changes whenever any plugin file changes
  rev: string
}

export interface Snapshot {
  queue: Job[]
  // the worker holds off starting queued jobs (the running one finishes)
  paused: boolean
  current: Progress | null
  recent: GalleryItem[]
  downloads: Download[]
}

export type WsMessage =
  | ({ type: 'snapshot' } & Snapshot)
  | { type: 'queue'; queue: Job[]; paused: boolean }
  | ({ type: 'progress' } & Progress)
  | { type: 'done'; job: Job }
  | { type: 'error'; jobId: string; message: string }
  | { type: 'download'; download: Download }
  | { type: 'models_changed' }
  | ({ type: 'identify' } & IdentifyState)
  | { type: 'model_defaults'; defaults: Record<string, ModelDefaults> }
  | { type: 'settings'; settings: Settings }
  // created or re-saved outside a job (external editor saves)
  | { type: 'gallery_item'; item: GalleryItem }
  | { type: 'grid'; grid: Grid }
  | { type: 'grid_removed'; id: string }
  | { type: 'plugins'; plugins: PluginInfo[] }
  // ctx.broadcast(event, data) from a plugin backend
  | { type: 'plugin'; plugin: string; event: string; data: unknown }
