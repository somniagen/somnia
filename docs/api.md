# API contract

Types are defined in `web/src/lib/types.ts` (camelCase JSON). Python side uses the same field names in JSON. All routes are under `/api` unless noted. Server port 7865.

## Jobs and queue (owner: server)
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/state` | | `Snapshot` |
| POST | `/api/jobs` | `{ params: GenParams, count?: number, repeat?: boolean }` | `{ ids: string[] }` (count = how many queued jobs, seed increments when seed != -1; `repeat` queues one job marked `repeat: true` that queues a copy of itself at the end of the queue each time it finishes, until it is cancelled, removed or fails) |
| DELETE | `/api/jobs/{id}` | | cancels running job or removes queued |
| POST | `/api/jobs/reorder` | `{ ids: string[] }` | `Job[]` |
| POST | `/api/jobs/clear` | | removes all queued (not running) |
| POST | `/api/jobs/stop-repeat` | | stops every repeating job from queueing more copies (the running one still finishes) |
| GET | `/api/presets` | | `Presets` |

`GenParams.variation` (`{enabled, seed, strength}`): when enabled with strength > 0 the base pass noise is slerped toward noise from `variation.seed` (+ batch index); queued counts keep the main seed and advance the variation seed (-1 = random per job). Only the base pass uses it. `upscale.tiled` (`{enabled, denoise, steps, tileSize, padding}`): after the final model upscale the image is refined by img2img tile by tile (tiles overlap by `padding`, feathered paste), progress phase `refine` with label `Tiled refine k/n`. Illustrious prompts may reference textual inversions as `embedding:name` or as a bare comma separated item equal to an embedding file stem (case-insensitive).

## Gallery / files (owner: server)
| GET | `/api/gallery` | `?cursor&limit&q&model&sort&fav&album` | `{ items: GalleryItem[], nextCursor }`. Unfiltered newest: stack roots only, ordered by the root's own creation time (adding to a stack does not move it), with `stackCount` / `stackCover` / `stackCoverItem` (the full cover item, used for tile aspect and lightbox browsing). With `q` (comma separated terms over prompt, model, loras, editor, seed; `-term` excludes; underscores equal spaces) or `model`, `fav=1` (favorites) or `album=name`: flat list including stack children. `sort` = newest, oldest, model; non-default sorts and filters page with `o:N` cursors |
| GET | `/api/gallery/models` | | `{ id, count }[]` models used in the gallery |
| PUT | `/api/gallery/{id}/favorite` | `{ favorite }` | `GalleryItem` |
| POST | `/api/gallery/favorite` | `{ ids, favorite }` | `GalleryItem[]` (bulk) |
| GET | `/api/gallery/albums` | | `GalleryAlbum[]` (`{ name, count, cover }`, cover = thumb of the newest member), sorted by name |
| POST | `/api/gallery/albums/add` | `{ ids, album }` | `GalleryItem[]`; name is whitespace-collapsed, max 80 chars; 400 when empty |
| POST | `/api/gallery/albums/remove` | `{ ids, album }` | `GalleryItem[]` |
| PUT | `/api/gallery/albums/{name}` | `{ name }` | `GalleryAlbum[]`; renames (merges into an existing album of that name) |
| DELETE | `/api/gallery/albums/{name}` | | `GalleryAlbum[]`; removes the album from all items (images stay) |
| POST | `/api/gallery/{id}/remove-bg` | | `GalleryItem`; `Settings.bgModel` cuts the background (`toonout`, default: BiRefNet fine-tuned on anime, onnx export `sprited/birefnet-toonout-onnx` fp16, 1024 square resize with imagenet normalization; `isnet`: skytnt/anime-seg `isnetis.onnx`, letterboxed; onnxruntime, CUDA when available, one session resident), saves an RGBA png (`alpha: true`, RGBA webp thumb, params copied, `sourceId`) stacked under the source's root, broadcasts `gallery_item`; requests are serialized |
| POST | `/api/gallery/{id}/upload` | | `UploadResult` (server side copy into uploads, for init images) |
| GET | `/api/gallery/{id}/stack` | | `GalleryItem[]` root first, then children oldest first (id may be any member) |
| PUT | `/api/gallery/{id}/cover` | | root `GalleryItem` with stack fields; makes stack member `id` (root or child) its stack's cover (`coverId` on the root) |
| POST | `/api/gallery/download` | `{ ids }` | one image: `image/png` attachment; more: `application/zip` of PNGs (stored, deduped); clients pass a stack's `stackCoverId` to export its cover |
| DELETE | `/api/gallery/{id}` | | |
| POST | `/api/upload` | multipart `file` | `UploadResult` (reads png params metadata if present) |
| GET | `/outputs/{name}` | | image file; thumbs at `/outputs/thumbs/{name}.webp` |
| GET | `/files/uploads/{id}.png` | | uploaded images and masks |

Masks are uploaded through `/api/upload` as a grayscale png (white = repaint).

Stacks: a job whose `params.stackId` names an existing root gallery item files its results under that root (`GalleryItem.stackId`); the key is stripped from saved params. Deleting a root promotes its oldest child (keeping a cover that is still in the stack). `stackCover` / `stackCoverId` is the root's `coverId` while it is a member, else the newest child. `live.recent` / snapshot `recent` include stack children. Roots also get `stackCoverAlpha` when the cover is transparent.

Favorites (`favorite: true`) and albums (`albums: string[]`) live in the item json; clients show a checkerboard (`--checker`) behind `alpha` items.

Uploaded png params (`/api/upload`, `read_params`): somnia json first, then A1111 `parameters` (sampler names and `Schedule type` mapped, `Model:` and `<lora:name:w>` matched to local files by name, hires as second pass), then ComfyUI `prompt` / `workflow` chunks (first KSampler(Advanced), text followed through links to CLIPTextEncode, checkpoint/UNET and LoraLoader chain, EmptyLatentImage size, CLIPSetLastLayer, a second sampler fed by the first as second pass).

## Settings / net (owner: server)
| GET | `/api/settings` | | `Settings` (civitaiToken and lanPassword returned masked) |
| PATCH | `/api/settings` | partial `Settings` | `Settings`, broadcasts `settings` |
| GET | `/api/net` | | `NetInfo` |

LAN: the server always binds `0.0.0.0`. A middleware returns 403 for non-loopback clients when `lanEnabled` is false. `/api/settings` writes are allowed only from loopback.

HTTPS: when `httpsCert` and `httpsKey` both name existing files, `python -m somnia` serves TLS with them (restart needed) and `/api/net` urls use `https://`.

## Auth (owner: server)
| GET | `/api/auth` | | `AuthStatus` `{required, ok}` |
| POST | `/api/auth/login` | `{password}` | `AuthStatus`, sets the `somnia_auth` cookie; 401 after ~1s on a wrong password |
| POST | `/api/auth/logout` | | `AuthStatus`, clears the cookie |

`lanPassword` is stored as a salted scrypt hash (`somnia/auth.py`). `GET /api/settings` returns `"****"` when set, `""` when not; PATCH a plain value to set it, `""` to clear it, `"****"` leaves it unchanged. With a password set, non-loopback clients need the cookie (httponly, SameSite=Lax, 1 year; an HMAC of a secret in `DATA_DIR/auth_secret` and the password hash, so changing the password signs everyone out) for `/api/*` (except `/api/auth*` and signed `/api/push/image/*`), `/ws`, `/outputs/*` and `/files/*`: http returns 401, `/ws` accepts then closes with code 4401. Setting a new password also closes open LAN sockets with 4401. The SPA shell, assets, `manifest.webmanifest`, `sw.js` and `icons/` stay public. Loopback is always allowed. The client shows a login screen when `/api/auth` is not ok or any call gets 401 / 4401, and reloads after login.

## Push notifications (owner: server)
| GET | `/api/push/key` | | `{key}` VAPID public key (base64url, generated once into `DATA_DIR/vapid_private.pem`) |
| POST | `/api/push/subscribe` | `{subscription: PushSubscriptionJson, label}` | `{endpoint, label}`, upserts by endpoint (`DATA_DIR/push_subscriptions.json`) |
| DELETE | `/api/push/subscribe` | `{endpoint}` | `{removed}` |
| POST | `/api/push/test` | `{endpoint?}` | `{sent}`, a test notification shown even when the app is focused |
| GET | `/api/push/image/{itemId}?sig=` | | thumbnail for notifications, signed so it works without the auth cookie |

Sent from a background thread by a `jobs.on_finish` hook: `Queue finished` with the image count since the last one and the last thumbnail when the queue drains, `Generation failed` on job errors. Payload `{title, body, tag, url, image?, icon?, force?}`. Subscriptions answering 404/410 are dropped. `sw.js` skips showing a notification while a Somnia window is focused and visible (unless `force`) and focuses or opens the app on click. Push needs a secure context (HTTPS or localhost); iOS only offers it to home screen apps.

PWA: `web/public/manifest.webmanifest`, `sw.js` (no fetch handler, everything goes to the network), `icons/`. The backend serves `sw.js` with `Service-Worker-Allowed: /` and `no-cache`, and fixes content types for js/css/webmanifest.

## Prompts (owner: server)
| GET | `/api/prompts` | | `SavedPrompt[]` |
| POST | `/api/prompts` | `SavedPrompt` without id/timestamps | `SavedPrompt` |
| PUT | `/api/prompts/{id}` | `SavedPrompt` | `SavedPrompt` |
| DELETE | `/api/prompts/{id}` | | |

## Models (owner: civitai/models)
| GET | `/api/models` | `?kind=` | `LocalModel[]` |
| POST | `/api/models/rescan` | | `LocalModel[]`, broadcasts `models_changed` |
| GET | `/api/models/preview/{id}` | | preview image if present |
| DELETE | `/api/models/{id}` | | moves file to `data/trash` |
| POST | `/api/models/identify` | | `IdentifyState`; starts a manual civitai hash lookup of every unidentified model (no-op while one runs) |
| GET | `/api/models/identify` | | `IdentifyState` |
| POST | `/api/models/updates` | | `{ changed }`; forces the civitai update check now |
| GET | `/api/models/defaults` | | `Record<modelId, ModelDefaults>` |
| PUT | `/api/models/defaults/{id}` | `{ params?: ModelDefaultParams, weight? }` | `ModelDefaults`; unknown params keys are dropped, 400 when nothing is left; broadcasts `model_defaults` |
| DELETE | `/api/models/defaults/{id}` | | broadcasts `model_defaults` |

Identify (`somnia/identify.py`): sha256 of the file (cached in `data/models_cache.json` as `sha:<path>`, or read from a fresh `<file>.sha256`) is looked up with civitai `model-versions/by-hash`; hits write `<file>.civitai.json`, misses are remembered for 7 days. Covers every kind except gguf. With `Settings.autoIdentify` (default true) it runs in the background on startup and after each rescan for new unidentified files only. Progress is broadcast as `{type:'identify', running, done, total}`; a civitai error ends the run early.

Updates: for identified models the civitai model's version list is cached in `data/civitai_updates.json` and refreshed at most once a day (hourly background loop, only with `autoIdentify`, and after an identify run that found something). When a newer version (civitai lists newest first) with the same `baseModel` exists and no newer version is installed, `LocalModel.civitai.updateVersionId` / `updateVersionName` are set (null otherwise); a change broadcasts `models_changed`.

Model defaults (`somnia/model_defaults.py`, `data/model_defaults.json`): checkpoints store `params` (steps, cfg, sampler, scheduler, clipSkip, cfgRescale, pag, vae, optionally width/height), loras a `weight`. Clients apply them when the user picks a model.

Model ids are `"{kind}:{relative/path.safetensors}"` relative to the model root folder of that kind.

Folders per kind inside each root in `Settings.modelRoots`:
- checkpoint: `checkpoints/`, `unet/`, `diffusion_models/` (anima transformer-only files live in unet/diffusion_models)
- lora: `loras/`, vae: `vae/`, text_encoder: `text_encoders/`, upscaler: `upscale_models/`, detector: `ultralytics/` (bbox and segm), embedding: `embeddings/` (textual inversions, `.safetensors`/`.pt`; `clip_l`+`clip_g` keys -> illustrious)

Family detection reads the safetensors header (SDXL keys like `conditioner.` / `model.diffusion_model.input_blocks` / `down_blocks` -> illustrious; `llm_adapter` / `net.blocks` / cosmos DiT keys -> anima). Loras are detected the same way from key names, else from civitai baseModel.

## Civitai (owner: civitai/models)
| GET | `/api/civitai/search` | `CivitaiSearchQuery` | `CivitaiSearchResult` |
| GET | `/api/civitai/models/{id}` | | `CivitaiModel` |
| GET | `/api/civitai/images` | `?modelVersionId&cursor&limit` | `{ items: CivitaiImage[], nextCursor }` |
| POST | `/api/civitai/download` | `{ versionId: number, fileId?: number }` | `Download` |
| GET | `/api/downloads` | | `Download[]` |
| DELETE | `/api/downloads/{id}` | | cancel |

Downloads write `<file>.civitai.json` (model + version json) and `<file>.preview.(png|jpeg|webp)` next to the model. Existing `.civitai.info` / `.metadata.json` sidecars from other UIs are read too.

## Hugging Face (owner: civitai/models)
| GET | `/api/hf/search` | `HfSearchQuery` (`query, category, sort, cursor, limit`) | `HfSearchResult`; repos with at least one file of `category` (or any recognized model file) |
| GET | `/api/hf/repo/{owner/name}` | `?category` | `HfRepoDetail` (files with detected kind, size, installed; readme text) |
| POST | `/api/hf/download` | `{ repo, path, kind, sub?, size? }` | `Download` (`source: 'hf'`, `repo`, `file`); 409 when the file exists |

`somnia/hf.py`: search uses the hub `/api/models` with `expand[]=siblings` and classifies each file (`classify`) by comfy folder names in its path (`diffusion_models/`, `vae/`, `upscale_models/`, `ultralytics/bbox`...), name patterns (`4x_`, esrgan, `vae`, `clip_l`, `lora`, `-seg`), repo tags (ultralytics, lora, textual-inversion) and size; diffusers subfolders, shards and gguf are skipped. Up to 4 hub pages are read per request until `limit` repos match. Empty queries browse a per category default (e.g. `filter=ultralytics` for bbox/segm, `upscale` for upscalers); an upscaler/vae query with no hits retries with that word added (cursor prefixed `s:`). Downloads go to `downloadRoot/<kind folder>` (`ultralytics/bbox|segm` for detectors), generic names (`model.safetensors`) become `<repo name>.safetensors`, `<file>.hf.json` records the source. `Settings.hfToken` (masked like `civitaiToken`) is sent for gated repos.

## Plugins (owner: server)
| GET | `/api/plugins` | | `PluginInfo[]` |
| POST | `/api/plugins/rescan` | | `PluginInfo[]` (loopback only) |
| POST | `/api/plugins/{id}/reload` | | `PluginInfo` (loopback only) |
| PUT | `/api/plugins/{id}` | `{ enabled }` | `PluginInfo` (loopback only) |
| GET | `/api/plugins/{id}/web/{path}` | | files next to the plugin's web entry |
| * | `/api/ext/{id}/...` | | the plugin's own backend routes |

`somnia/plugins.py` polls `plugins/` every second and loads, reloads or unloads plugins whose files changed (`PluginInfo.rev`), broadcasting `{type:'plugins', plugins}`; plugin events arrive as `{type:'plugin', plugin, event, data}`. The client (`lib/plugins.svelte.ts`) re-imports a web entry whenever its `rev` changes. See `docs/plugins.md`.

## Tags (owner: tags)
| GET | `/api/tags/search` | `?q&limit=20` | `Tag[]` (prefix + alias match, sorted by count; `q` uses spaces or underscores) |
| GET | `/api/tags/wiki/{name}` | | `TagWiki` (danbooru wiki, cached on disk; body is plain text with dtext stripped to light markdown) |
| GET | `/api/tags/related/{name}` | `?limit=16` | `RelatedTag[]` tags that co-occur with `name` on danbooru, most similar first, meta tags dropped (cached on disk) |
| GET | `/api/tags/lookup` | `?names=a,b,c` | `Record<string, TagCategory>` for coloring existing prompt tags |

## Inpaint helpers (owner: inpainter)
| POST | `/api/detect` | `{ imageId, detector, confidence }` | `Detection[]` (maskUrl is a png in uploads when the detector is a segm model, else null and bbox is used) |

## Image editors (owner: server)
| GET | `/api/editors` | `?rescan` | `EditorList` (`local` false and empty for non-loopback clients) |
| GET | `/api/editors/{id}/icon` | | png app icon extracted from the executable (windows), 404 otherwise |
| POST | `/api/editors/browse` | | `{ path, name }` opens a native file picker on the server machine (null when cancelled); loopback only |
| POST | `/api/editors/custom` | `{ path, name? }` | `EditorList`, adds a program (name from its version info when omitted) and selects it; loopback only |
| PUT | `/api/editors/custom/{id}` | `{ name }` | `EditorList`, renames |
| DELETE | `/api/editors/custom/{id}` | | `EditorList` |
| POST | `/api/editors/open` | `{ url, editor?, galleryId? }` | `{ editor, session }`; copies the image to `data/editing/{session}/` and opens the copy (setting `imageEditor`, or the first detected); loopback only |

Editing sessions (`somnia/editing.py`): a watcher polls the copy; each save (file changed, then stable for a poll) writes one gallery item, `editedWith: {id, name}`, stacked under the source's stack, re-saves overwrite it (url gets `?v=`), broadcast as `{type:'gallery_item', item}`. When the editor's process is gone (after a startup grace) the folder is deleted. Sessions resume after a server restart.

Detected on windows: every Adobe Photoshop version (named without "Adobe", newest first), Krita, Paint.NET. macOS: Photoshop apps and Krita. Linux: krita on PATH.

## X/Y/Z grids (owner: server)
| POST | `/api/grids` | `{ base: GenParams, axes: GridAxis[] }` (1-3 axes: x, y, z) | `Grid`; 400 when an axis is empty or there are more than 500 cells |
| GET | `/api/grids` | `?limit=20` | `Grid[]` newest first |
| GET | `/api/grids/{id}` | | `Grid` |
| DELETE | `/api/grids/{id}` | | cancels its remaining jobs and forgets the grid (images stay in the gallery), broadcasts `{type:'grid_removed', id}` |

`somnia/grids.py`: every combination is queued in z, y, x order through `jobs.submit(meta=...)` (jobs carry `grid: {id, x, y, z}`), `batchSize` forced to 1, one shared seed unless an axis sets `seed`. A cell's patch is the deep merge of its x/y/z value patches; the backend is generic except two ops: `"$sr": [search, replace]` replaces text in prompt, negative and `segments` (applied in axis order), `"$lora": {id, weight}` sets one lora weight (added when missing). A `variation` patch gets a concrete variation seed. Cells finish through `jobs.on_finish`; queued cells whose job disappears (removed from the queue, restart) become `cancelled` after ~3s. Each change is persisted (sqlite `grids`) and broadcast as `{type:'grid', grid}`. Once no cell is queued the grid becomes `composing`, then per z value a labeled image (x labels on top, y labels on the left, z title) is saved as a gallery item (`grid: {id, z}`, `coverId` = itself) and the cell images of that z are re-filed as its stack children; `status` ends `done` (or `failed` when no cell produced an image) and the items are broadcast as `gallery_item`.

## Websocket `/ws`
On connect the server sends `{type:'snapshot', ...Snapshot}` immediately, then deltas (`WsMessage` in types.ts). `progress` is throttled to ~10/s; `preview` is a `data:image/jpeg;base64,...` url and only present on messages that carry a new preview. `step`/`total` always describe the current phase (sampling steps, upscaler tiles, decode tiles, per-detection detailer steps); `label` is an optional human readable sub-phase (e.g. `Detailer face 2/3`, `Upscaling`, `Second pass`) or null. Previews are decoded from the predicted clean image (x0) with a tiny VAE. During detailer and tiled refine steps `region` (`{x, y, w, h}`, fractions of the whole image) marks the area being rendered and `preview` is the whole image (up to 1024px) with the area's preview pasted in; otherwise `region` is null. Clients never control job lifetime by connecting or disconnecting. `identify` carries civitai hash lookup progress, `model_defaults` the full defaults record after any change, `plugins` the plugin list after any load/unload.

## Python module contracts
- `somnia.config`: `DATA_DIR`, `ROOT`, `settings()` -> `Settings` dataclass, `update_settings(**kw)`.
- `somnia.models`: `list_models(kind=None) -> list[dict]`, `resolve(id) -> Path`, `rescan()`, `get(id) -> dict | None`, `detect_family(path) -> str | None`.
- `somnia.engine.base`: see file. `somnia.engine.pipeline.run(params: dict, ctx: RunContext) -> list[PIL.Image]` is the single entry point the queue worker calls.
- `somnia.presets`: `presets() -> dict` matching `Presets`.
- `somnia.hub`: `hub.broadcast(msg: dict)` thread-safe from the worker thread.
