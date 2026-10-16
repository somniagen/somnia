# Somnia

Local image-gen WebUI for Illustrious (SDXL, e.g. WAI-Illustrious-SDXL v17) and Anima (e.g. AnimaYume 1.5). Python (FastAPI + pure diffusers/torch) backend, Svelte 5 + Vite + TS frontend.

## Layout
- `backend/somnia/` python package. Run: `.venv/Scripts/python -m somnia` (from `backend/`, or with `PYTHONPATH=backend`). Port 7865.
- `web/` frontend. `npm run dev` (proxies to backend) / `npm run build` (served by backend from `web/dist`).
- `docs/api.md` is the frozen REST + websocket contract. `web/src/lib/types.ts` mirrors it. Change both together.
- `backend/somnia/engine/base.py` is the engine contract.
- Test models: `D:\ComfyUI_windows_portable_nvidia_cu128\ComfyUI_windows_portable\ComfyUI\models` (checkpoints, unet, text_encoders, vae, loras, upscale_models, ultralytics).
- Python env: `uv sync` (torch cu128, python 3.12). Add deps to `pyproject.toml`, never pip install ad hoc.

## Requirements
- Simple, UX focused, workstation-like UI. Very dark neutral background (`--bg` / `--grad-bg` in tokens), no tinted grays. Surfaces and raised controls use the `--grad-*` gradient tokens plus `--sheen` top highlights. Primary/highlighted buttons are white; color only for semantic state (danger red, success, warning) and tag colors.
- Glowing top progress bar (leading edge glows), status line shows crawling hazard stripes while running.
- Built-in model manager: browse/pull/sort models and loras from Civitai, view examples and their prompts.
- Customizable params with high-quality defaults for WAI-Illustrious v17 and AnimaYume 1.5, plus quality tools (second pass/hires, detailer, upscalers, PAG...).
- Responsive, works well on mobile.
- Painless install (`install.bat` / `install.sh`, uv based).
- Toggle for exposing the UI on the local network.
- Queue; current generation spectatable from multiple devices; switching device never interrupts it.
- Upscaling and double ksampler (second pass).
- Interactive inpainter: smart high-quality mask painting, preview, YOLO autoselect.
- Saved prompts; marking prompt parts as boilerplate (locked, greyed). LoRA trigger words suggested as boilerplate.
- Danbooru tag autocomplete, wiki popup on hover, tag category coloring in the prompt box.
- Reusable UI primitives in `web/src/lib/ui` (built first, used everywhere).

## UI rules
- Very little text. Explanations go behind an `InfoTip` (i) icon.
- No off-black background, no pill-shaped buttons, no small all-caps headers, no "01/02/03" section labels.
- IBM Plex Sans, Material Symbols icons.
- Containers (cards, panels, popovers, sheets) get a 1px hairline border plus surface elevation; controls stay mostly borderless. Danger actions red, desirable actions accent-highlighted.
- Thoughtful details (seed dice/lock, aspect preview, drag-in image to reuse params, good empty states, press feedback).

## Code rules
- Avoid code comments unless something really needs explaining; lowercase comments.
- No non-standard characters (em-dashes etc.) in code.
- Match existing idioms. Use tokens from `web/src/lib/ui/tokens.css`, never hardcode colors.

## Features
When you finish a feature, add one short line here.
- scaffold: repo layout, api contract, engine contract, design tokens
- ui primitives: `web/src/lib/ui` (see its README.md), demo at `#/ui`
- models + civitai: local model scan with header family detection and sidecars, civitai browse API, resumable download manager (needs civitai token for most files)
- tags: danbooru tag search/lookup (in-memory index, background load), cached wiki popups (`/api/tags/*`, `scripts/fetch_tags.py`, `scripts/test_tags.py`)
- installer: install.bat/install.sh (uv, torch cu128, frontend build), run.bat/run.sh, README
- frontend client: typed rest client (web/src/lib/api.ts), live ws state store with auto-reconnect (web/src/lib/live.svelte.ts)
- server: fastapi app, queue worker, ws hub, gallery, settings, prompts (sqlite); test: .venv/Scripts/python scripts/test_server.py
- illustrious engine + pipeline: sdxl single-file engine (a1111 weighting/long prompts, samplers x schedulers, lora stack, pag, img2img/inpaint, taesd previews), second pass, yolo detailers, spandrel upscale, presets; test: scripts/smoke_illustrious.py
- models UI: library/civitai manager with downloads, ModelSelect and LoraPicker (web/src/features/models)
- prompt editor: boilerplate locking (drag handle / Alt+Arrow reorder, auto color by kind + swatch menu, `PromptSegment.color`), tag coloring, danbooru autocomplete, wiki hover, touch: tap tag for docked card with lock, docked autocomplete and selection lock above the keyboard, lora trigger chips, saved prompt library (`web/src/features/prompt`, dev at `#/dev/prompt`)
- inpainter: `web/src/features/inpaint` full-screen mask editor (soft/pressure brush, smart select, YOLO detect via `/api/detect` bbox+segm, grow/feather, overlay/outline/mask/edge previews, pinch zoom), playground at `#/dev/inpaint`
- main app: shell (router, glow bar, rail/tab bar), generate view (params panel, live preview, queue, recent), gallery + lightbox, settings (`web/src/App.svelte`, `web/src/features/{shell,generate,gallery,queue,settings}`)
- anima engine: pure torch port of comfy Anima (cosmos predict2 dit + llm adapter, qwen3 te, wan/qwen-image vae), txt2img/img2img/inpaint, loras, er_sde/euler/euler_a/dpmpp_2m (`somnia.engine.anima`, `scripts/smoke_anima.py`)
- app polish: status line + per-phase glow bar (shell/StatusLine), collapsing mobile preview header, newest-first gallery with created-time cursors, rebuilt lightbox (zoom/pan/swipe/filmstrip/details sheet), short-side resolution picker (illustrious 1024, anima 16px steps), Somnia logo + favicon
- memory + previews + speed: one model resident (no cpu copies), pinned TE/VAE parking (`engine/mem.py`), cached prompt encodings, tiled decode/upscale, true latent second pass (`latent`, `latent-bislerp`, `latent-nearest`), x0 previews via TAESD-XL / TAEW2.1 (`engine/previews.py`), progress `label`, `nvidiaOptimizations` (tf32 + fp16 accumulation, fp16 Anima with bf16 fallback, `engine/optim.py`); bench: `scripts/mem_bench.py`, `scripts/speed_bench.py`, `scripts/mem_trace.py`
- look refresh: darker palette, gradient tokens (`--grad-1..4`, `--grad-accent`, `--grad-danger`, `--grad-progress`, `--sheen`, `--stripes`) used by all primitives, stronger glow bar, striped running status line
- inpaint tab: `#/inpaint` (`features/inpaint/InpaintView.svelte`, state in `studio.svelte.ts`) with its own prompt/denoise/context/steps/cfg/seed, render-area overlay, live preview inside the area, version strip with cancel, hold `\` to compare with the original; mask editor embeds via `embedded` + `settings`/`bar`/`stage` snippets and `exportMask()`
- mask editor: roto style smart brush (`features/inpaint/smart.ts`, marker watershed with color-model outside markers + guided filter, add/remove, live while painting, seeds only from the committed mask), photoshop shortcuts (alt right drag resize, shift click lines, ctrl 0/1/+/-, ctrl D/A/shift I, Q, H, Tab, `?` overlay)
- gallery stacks: `params.stackId` files results under a root (`stack`/`sort` columns, `/api/gallery/{id}/stack`), roots show a layered tile, gallery masonry fills columns in row order
- prompt weights + related tags: Ctrl/Cmd+Up/Down steps `(tag:1.1)` weight on the selection or item at the caret (Shift for 0.05, `reweight`/`weightAt` in `tokenize.ts`), weight stepper in the mobile tag card and selection dock; hover/tag cards suggest co-occurring tags (`/api/tags/related/{name}`, danbooru related_tag, cached in `data/tags/related`), one tap adds them; mobile tag card opens on a second tap on the same tag and closes on typing or selecting
- external image editors: `somnia/editors.py` detects Photoshop (every version, named without "Adobe"), Krita, Paint.NET, extracts app icons via win32; `OpenInEditor` button (lightbox, generate preview, inpaint) only for loopback clients; `imageEditor` setting picks one (`""` auto, `"none"` off); `customEditors` adds any program by path or native browse dialog (`/api/editors/custom`, `/api/editors/browse`)
- editor round trip: opening in an editor edits a copy (`somnia/editing.py`), saves become a gallery item stacked with the source and marked `editedWith` (badge + lightbox note), the copy is deleted once the editor app exits
- gallery search/sort (`q`, `model`, `sort` on `/api/gallery`), detailer `appendPrompt`, `GenParams.segments` saves boilerplate segments with each image and reuse restores them
