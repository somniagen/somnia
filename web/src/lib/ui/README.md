# UI primitives

Import from `src/lib/ui` (`import { Button, Slider, toast } from '../lib/ui'`). Live demo at `#/ui` (`Demo.svelte`).
Look: very dark neutral grays with subtle vertical gradients (`--grad-1..4` match `--surface-1..4`, raised controls add `--sheen`), white gradient accent (`--grad-accent`, primary buttons white and softly glowing), color only for state and tags. Containers (Surface/Card, Modal, Popover, sheets, tiles) get a 1px `--hairline` border; nested Surfaces drop it.
All components accept `class` and `style`; most spread extra HTML attributes. Values are `bind:`able. Touch targets grow to 44px on coarse pointers.
Items lists (`Select`, `WheelPicker`, `Segmented`, `Tabs`) take plain values or `{ value, label?, icon?, hint?, disabled? }`.

| Component | Key props |
| --- | --- |
| `Button` | `variant` primary/default/ghost/danger, `size` sm/md, `icon`, `iconRight`, `loading`, `full` |
| `IconButton` | `icon`, `label` (aria + tooltip), `variant`, `size`, `active` (pressed), `tip` placement or false |
| `Toggle` | `bind:checked`, `label`, `size`, `onchange` |
| `Checkbox` | `bind:checked`, `indeterminate`, `label` |
| `Slider` | `bind:value`, `min max step`, `defaultValue` (dblclick / Delete resets), `marks`, `editable`, `format`, `label`; shift-drag = fine |
| `NumberField` | `bind:value`, `min max step`, `label` (drag to scrub, shift fine, dblclick reset), `icon`, `suffix`, `steppers`, wheel when focused |
| `WheelPicker` | `items`, `bind:value`, `visible`, `itemHeight`, `item` snippet `(item, selected)` |
| `Select` | `items`, `bind:value`, `placeholder`, `label`, `searchable` (auto when > 8), `item` snippet; BottomSheet on mobile |
| `Combobox` | `bind:value` (text), `search(q, signal)` async, `onselect`, `getLabel`, `clearOnSelect`, `item` / `empty` snippets |
| `Segmented` | `items`, `bind:value`, `size`, `full`, `iconOnly` |
| `Tabs` | `items`, `bind:value`, `children(value)` snippet renders the panel |
| `InfoTip` | `text` or children, `placement`; hover/focus on desktop, tap on touch |
| `tooltip` | action: `use:tooltip={'text'}` or `{ text, placement, delay }` |
| `Popover` | `bind:open`, `anchor` (element or `{x,y}`), `placement`, `matchWidth`, `autofocus`, `dismissible`; flips, closes on outside/Escape |
| `Modal` | `bind:open`, `title`, `width`, `dismissible`, `footer` / `header` snippets |
| `BottomSheet` | `bind:open`, `title`, `snaps` (viewport fractions, e.g. `[0.5, 0.9]`), `bind:snap`, swipe down dismiss |
| `Sheet` | Modal on desktop, BottomSheet at <= 640px; union of their props |
| `toast` / `Toaster` | mount `<Toaster />` once; `toast.success/error/info(msg, { description, action: { label, run }, duration })` |
| `GlowProgressBar` | `value` 0..1 or `null` (indeterminate), `status` idle/running/success/error, `fixed` (top of viewport), `height` |
| `Surface` | `level` 0-4, `padding`, `radius`, `as`, `interactive`, `bordered` |
| `Card` | Surface + `title`, `icon`, `actions` snippet |
| `Field` | `label`, `info` (InfoTip), `hint`, `error`, `inline`, `trailing` snippet, `children(id)` snippet gets the control id |
| `ImageTile` | `src`, `aspect` (number or `'2:3'`), `fit`, `bind:selected`, `selectable`, `onclick`, `actions` / `badge` snippets |
| `Dropzone` | `onfiles(files)`, `accept`, `multiple`, `paste` (window paste), `compact`, `title`, `hint`, children(over) |
| `Chip` | `label`, `color` (css color or token like `'--tag-artist'`), `locked`, `removable` + `onremove`, `selected`, `onclick`, `size` |
| `Menu` | `items: MenuItem[]` (`label icon danger disabled shortcut checked onselect` or `{ separator: true }`), `trigger` snippet `({ open, toggle })` or `anchor` + `bind:open` (context menus: anchor `{x,y}`) |
| `SeedField` | `bind:value`, `bind:locked`, `max`; dice randomizes |
| `AspectPicker` | `bind:width`, `bind:height`, `options: [w,h][]`, `custom` (W/H fields), `step min max` |
| `EmptyState` | `icon`, `title`, `description`, `compact`, children = actions |
| `Skeleton`, `Spinner`, `Kbd` | `width height radius circle` / `size label` / children |

Helpers: `mobile`, `coarse`, `reducedMotion` (reactive `MediaQuery`, read `.current`), `clamp`, `portal` action.
