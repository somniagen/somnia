# API contract

Types are defined in `web/src/lib/types.ts` (camelCase JSON). Python side uses the same field names in JSON. All routes are under `/api` unless noted. Server port 7865.

## Jobs and queue (owner: server)
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/state` | | `Snapshot` |
| POST | `/api/jobs` | `{ params: GenParams, count?: number }` | `{ ids: string[] }` (count = how many queued jobs, seed increments when seed != -1) |
| DELETE | `/api/jobs/{id}` | | cancels running job or removes queued |
| POST | `/api/jobs/reorder` | `{ ids: string[] }` | `Job[]` |
| POST | `/api/jobs/clear` | | removes all queued (not running) |
| GET | `/api/presets` | | `Presets` |

## Gallery / files (owner: server)
| GET | `/api/gallery` | `?cursor&limit&q&model&sort` | `{ items: GalleryItem[], nextCursor }`. Unfiltered newest: stack roots only, ordered by latest stack activity, with `stackCount` / `stackCover`. With `q` (comma separated terms over prompt, model, loras, editor, seed; `-term` excludes; underscores equal spaces) or `model`: flat list including stack children. `sort` = newest, oldest, model; non-default sorts and filters page with `o:N` cursors |
| GET | `/api/gallery/models` | | `{ id, count }[]` models used in the gallery |
| POST | `/api/gallery/{id}/upload` | | `UploadResult` (server side copy into uploads, for init images) |
| GET | `/api/gallery/{id}/stack` | | `GalleryItem[]` root first, then children oldest first (id may be any member) |
| DELETE | `/api/gallery/{id}` | | |
| POST | `/api/upload` | multipart `file` | `UploadResult` (reads png params metadata if present) |
| GET | `/outputs/{name}` | | image file; thumbs at `/outputs/thumbs/{name}.webp` |
| GET | `/files/uploads/{id}.png` | | uploaded images and masks |

Masks are uploaded through `/api/upload` as a grayscale png (white = repaint).

Stacks: a job whose `params.stackId` names an existing root gallery item files its results under that root (`GalleryItem.stackId`); the key is stripped from saved params. Deleting a root promotes its oldest child. `live.recent` / snapshot `recent` include stack children.

## Settings / net (owner: server)
| GET | `/api/settings` | | `Settings` (civitaiToken returned masked) |
| PATCH | `/api/settings` | partial `Settings` | `Settings`, broadcasts `settings` |
| GET | `/api/net` | | `NetInfo` |

LAN: the server always binds `0.0.0.0`. A middleware returns 403 for non-loopback clients when `lanEnabled` is false. `/api/settings` writes are allowed only from loopback.

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

Model ids are `"{kind}:{relative/path.safetensors}"` relative to the model root folder of that kind.

Folders per kind inside each root in `Settings.modelRoots`:
- checkpoint: `checkpoints/`, `unet/`, `diffusion_models/` (anima transformer-only files live in unet/diffusion_models)
- lora: `loras/`, vae: `vae/`, text_encoder: `text_encoders/`, upscaler: `upscale_models/`, detector: `ultralytics/` (bbox and segm)

Family detection reads the safetensors header (SDXL keys like `conditioner.` / `model.diffusion_model.input_blocks` / `down_blocks` -> illustrious; `llm_adapter` / `net.blocks` / cosmos DiT keys -> anima). Loras are detected the same way from key names, else from civitai baseModel.

## Civitai (owner: civitai/models)
| GET | `/api/civitai/search` | `CivitaiSearchQuery` | `CivitaiSearchResult` |
| GET | `/api/civitai/models/{id}` | | `CivitaiModel` |
| GET | `/api/civitai/images` | `?modelVersionId&cursor&limit` | `{ items: CivitaiImage[], nextCursor }` |
| POST | `/api/civitai/download` | `{ versionId: number, fileId?: number }` | `Download` |
| GET | `/api/downloads` | | `Download[]` |
| DELETE | `/api/downloads/{id}` | | cancel |

Downloads write `<file>.civitai.json` (model + version json) and `<file>.preview.(png|jpeg|webp)` next to the model. Existing `.civitai.info` / `.metadata.json` sidecars from other UIs are read too.

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

## Websocket `/ws`
On connect the server sends `{type:'snapshot', ...Snapshot}` immediately, then deltas (`WsMessage` in types.ts). `progress` is throttled to ~10/s; `preview` is a `data:image/jpeg;base64,...` url and only present on messages that carry a new preview. `step`/`total` always describe the current phase (sampling steps, upscaler tiles, decode tiles, per-detection detailer steps); `label` is an optional human readable sub-phase (e.g. `Detailer face 2/3`, `Upscaling`, `Second pass`) or null. Previews are decoded from the predicted clean image (x0) with a tiny VAE. Clients never control job lifetime by connecting or disconnecting.

## Python module contracts
- `somnia.config`: `DATA_DIR`, `ROOT`, `settings()` -> `Settings` dataclass, `update_settings(**kw)`.
- `somnia.models`: `list_models(kind=None) -> list[dict]`, `resolve(id) -> Path`, `rescan()`, `get(id) -> dict | None`, `detect_family(path) -> str | None`.
- `somnia.engine.base`: see file. `somnia.engine.pipeline.run(params: dict, ctx: RunContext) -> list[PIL.Image]` is the single entry point the queue worker calls.
- `somnia.presets`: `presets() -> dict` matching `Presets`.
- `somnia.hub`: `hub.broadcast(msg: dict)` thread-safe from the worker thread.
