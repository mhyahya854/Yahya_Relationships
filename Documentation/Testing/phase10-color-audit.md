# Phase 10 Color Audit

## Result

PASS. The application now has one semantic Light/Dark token system sourced exclusively from the palette supplied with Phase 10. A source scan of `Codebase/App/Frontend/src` finds hexadecimal color literals only in the two token-definition blocks in `styles.css`; application rules consume semantic variables.

## Theme architecture

- Light is the default theme.
- Dark is applied with `html[data-theme="dark"]`.
- `ThemeProvider` owns the UI preference and persists `light` or `dark` in `localStorage` under `people-relationships.theme`.
- Theme storage is independent of DataRoot state and requires no family schema migration.
- `color-scheme` changes with the active theme, including first-run, recovery, dialogs, graph canvases, Journal, and Hermes.

## Semantic token mapping

| Semantic role | Light palette entry/value | Dark palette entry/value |
|---|---|---|
| Application canvas | Cool white bg `#F8FAFB` | Cool white bg `#25292C` |
| Primary surface | Pure white bg `#FFFFFF` | Pure white bg `#252522` |
| Secondary surface | Soft white bg `#FCFBF8` | Soft white bg `#272725` |
| Elevated surface | Warm white bg `#FAF8F2` | Warm white bg `#292722` |
| Glass surface | Mint bg `#EBF6F4` | Mint bg `#17201F` |
| Primary text | Pure white fg `#37352F` | Pure white fg `#FFFFFF` |
| Secondary text | Cool gray fg `#50585F` | Cool gray fg `#CCD3D8` |
| Tertiary text | Warm gray fg `#59534C` | Gray 500 fg `#B7B7B1` |
| Subtle border | Light gray 200 bg `#E2E2DD` | Light gray 200 bg `#343532` |
| Strong border | Gray 400 bg `#BDBDB7` | Gray 500 bg `#484945` |
| Primary accent | Jade fg `#005F48` | Jade fg `#96C7B5` |
| Accent hover | Emerald fg `#085F3D` | Emerald fg `#99C7AD` |
| Accent selection | Jade bg `#E5F9F1` | Jade bg `#12221C` |
| Success | Emerald `#085F3D` / `#E6F9EE` | Emerald `#99C7AD` / `#13221A` |
| Warning | Amber `#654300` / `#FDF2E2` | Amber `#D0B690` / `#251D10` |
| Danger | Red `#833128` / `#FFEDE8` | Red `#E7A99F` / `#2C1815` |
| Information | Azure `#34558A` / `#EAF4FF` | Azure `#A3BCE4` / `#171E2B` |
| Focus ring | Teal fg `#005D61` | Teal fg `#93C5C8` |
| Disabled | Gray 300/Neutral gray | Gray 300/Gray 500 |
| Maternal branch | Pink-red fg/bg `#783944` / `#FFEDF0` | `#DDACB2` / `#29191B` |
| Paternal branch | Blue fg/bg `#3F518E` / `#ECF3FF` | `#A9B9E7` / `#191D2C` |
| Family line | Forest green fg `#325A41` | Forest green fg `#A7C3AF` |
| General line | Cyan fg `#005877` | Cyan fg `#94C2D9` |
| Marriage line | Violet fg `#643F6D` | Violet fg `#CBB0D1` |
| Sibling line | Neutral gray fg `#555653` | Neutral gray fg `#CFD0CB` |
| Adopted/foster line | Amber fg `#654300` | Amber fg `#D0B690` |
| Graph canvas/dots | Cool white/Gray 300 | Cool white/Gray 400 |
| Technical block | Ink bg/fg pair | Ink bg/fg pair |

## Token families

The reusable roles are defined at the root and remapped once for Dark mode:

- surfaces: `--app-bg`, `--surface-primary`, `--surface-secondary`, `--surface-elevated`, `--surface-glass`, `--surface-overlay`;
- text and structure: `--text-primary`, `--text-secondary`, `--text-tertiary`, `--border-subtle`, `--border-strong`;
- interaction: `--accent-primary`, `--accent-hover`, `--accent-selected`, `--focus-ring`, `--disabled-bg`, `--disabled-fg`;
- status: `--status-success`, `--status-warning`, `--status-danger`, `--status-info` plus their backgrounds;
- graph: `--maternal`, `--paternal`, `--relationship-line`, `--family-line`, `--general-line`, `--marriage-line`, `--sibling-line`, `--adopted-line`, `--derived-line`, `--graph-canvas`, `--graph-dot`;
- technical/depth: `--code-bg`, `--code-fg`, `--backdrop`, `--shadow-subtle`, `--shadow-strong`.

Legacy variable names remain only as compatibility aliases that resolve to these semantic tokens. They do not introduce additional colors.

## Hard-coded value scan

Command:

```powershell
rg -n --glob '!node_modules/**' --glob '!dist/**' --glob '!tsconfig.tsbuildinfo' '#[0-9A-Fa-f]{3,8}|rgba?\(|hsla?\(' Codebase/App/Frontend/src
```

Result:

- hexadecimal literals occur only in the Light and Dark semantic token blocks in `styles.css`;
- no component `.tsx` file contains a hard-coded UI color;
- no `rgb()`, `rgba()`, `hsl()`, or `hsla()` application color is present;
- translucency and derived depth use `color-mix()` from palette-backed semantic tokens and `transparent`, so no unrelated hue is introduced.

## Focused visual assertions

The Phase 10 visual suite proves:

- theme switching updates `color-scheme`, semantic tokens, graph canvas, dots, and rendered edges immediately;
- theme preference survives reload and DataRoot recovery boundaries;
- an already-open dialog updates Light → Dark → Light without restart;
- success, warning, and danger tokens remain distinct;
- dark Journal surface/editor, read-only warning, and dialogs remain visibly distinct;
- Family Tree nodes remain interactive in Dark mode.

## Justified exceptions

No hard-coded application-surface color exceptions remain. Browser-native transparency and third-party geometry internals are not new palette colors and inherit the semantic token styling applied by the application.
