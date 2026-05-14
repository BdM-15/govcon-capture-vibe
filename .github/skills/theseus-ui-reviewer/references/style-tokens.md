# Style Tokens — `:root` Catalog

The single source of truth for color in Theseus. **Every color in the UI must reference one of these tokens via `var(--*)` (CSS) or the matching Tailwind utility (`bg-neon-cyan`, `text-text-300`, `border-edge-strong`).** Raw hex literals are forbidden when a token covers the value.

The full catalog lives in [`src/ui/static/styles/theseus.css`](../../../../src/ui/static/styles/theseus.css) under the `:root` block. This reference is a curated subset for review.

## Reference Pattern

```css
/* CORRECT — reference the token */
.cta { color: var(--neon-cyan); border: 1px solid var(--edge-strong); }

/* WRONG — raw hex */
.cta { color: #00f0ff; }
```

## Brand Neon

| Token                  | Hex       | Use                                                          |
| ---------------------- | --------- | ------------------------------------------------------------ |
| `--neon-cyan`          | `#00f0ff` | Primary brand accent. Doctrine tier border. Focus rings.     |
| `--neon-cyan-rgb`      | triplet   | For `rgba(var(--neon-cyan-rgb), <alpha>)` transparency.      |
| `--neon-magenta`       | `#ff2bd6` | Intelligence tier border. Secondary accent.                  |
| `--neon-magenta-rgb`   | triplet   | Same usage pattern as cyan.                                  |
| `--neon-amber`         | `#ffb020` | Pursuit tier border. Warning / degraded state.               |
| `--neon-amber-rgb`     | triplet   | Same usage pattern.                                          |
| `--neon-lime`          | `#00ff9c` | Success / live state.                                        |
| `--neon-red`           | `#ff3b6b` | Error / critical state.                                      |

## Ink Scale (Dark Surfaces)

| Token       | Hex       | Use                                              |
| ----------- | --------- | ------------------------------------------------ |
| `--ink-950` | `#05070d` | Deepest background, behind everything.           |
| `--ink-900` | `#0a0e1a` | Page background.                                 |
| `--ink-850` | `#0f1422` | Modal / drawer background.                       |
| `--ink-800` | `#141a2b` | Card / chip background.                          |
| `--ink-700` | `#1c2338` | Hover surface.                                   |
| `--ink-card` | `#11172a` | Standard card background.                       |

## Edges

| Token            | Hex       | Use                                          |
| ---------------- | --------- | -------------------------------------------- |
| `--edge`         | `#1f2a44` | Default 1px borders, dividers.               |
| `--edge-strong`  | `#2c3a5e` | Emphasized borders, card outlines.           |

## Text

| Token            | Hex       | Use                                          |
| ---------------- | --------- | -------------------------------------------- |
| `--text-primary` | `#e6ecff` | Primary body text on dark surfaces.          |
| `--text-300`     | `#cbd5e1` | Secondary text, labels.                      |
| `--text-500`     | `#64748b` | Tertiary, placeholders, disabled.            |

## Shadows / Glows

| Token             | Effect                                                          |
| ----------------- | --------------------------------------------------------------- |
| `--shadow-glow`   | Standard cyan neon glow for focus / active states.              |
| `--shadow-magenta`| Magenta variant for intelligence-tier surfaces.                 |

## Transparency Pattern

Never invent a hex variant for transparency. Use the `--*-rgb` triplet:

```css
/* CORRECT */
background: rgba(var(--neon-cyan-rgb), 0.4);

/* WRONG — invented hex variant */
background: #00f0ff66;
```

## Tailwind Mirror

Custom tokens are exposed as Tailwind utilities via the inline `tailwind.config = {…}` script in `src/ui/static/index.html` AND mirrored in `tailwind.config.js`. If you add a new token to `:root`, mirror it in **both** config locations or the utility class won't exist.

Sanctioned utility names: `bg-neon-cyan`, `bg-neon-magenta`, `bg-neon-amber`, `bg-ink-900`, `bg-ink-800`, `border-edge-strong`, `text-text-300`, `shadow-glow`, `shadow-magenta`.
