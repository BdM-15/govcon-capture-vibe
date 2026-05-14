# Anti-Patterns (Banned Constructs)

Findings cite the **rule name** from this file (e.g. `rule: "raw-hex-vs-token"`).

## `raw-hex-vs-token` — CRITICAL

A raw hex literal in CSS or inline style where a `:root` token covers the value.

**Bad:**

```css
.thing { color: #00f0ff; }
```

```html
<div class="bg-[#00f0ff]">…</div>
```

**Good:**

```css
.thing { color: var(--neon-cyan); }
```

```html
<div class="bg-neon-cyan">…</div>
```

**Fix string template:** ``use `var(--neon-cyan)` instead of raw hex `#00f0ff`.``

## `apply-leak-in-external-css` — CRITICAL

`@apply` inside `theseus.css` (or any external CSS file). Tailwind Play CDN does NOT process `@apply` outside an inline `<style>` block in `index.html`. Silently breaks styles.

**Bad (in `theseus.css`):**

```css
.btn { @apply bg-neon-cyan text-ink-900 px-3 py-1 rounded; }
```

**Good:**

```css
.btn {
  background: var(--neon-cyan);
  color: var(--ink-900);
  padding: 0.25rem 0.75rem;
  border-radius: 0.375rem;
}
```

## `invented-hex-variant` — MAJOR

Adding a new hex literal for a transparency or shade variant of an existing token. Use the `--*-rgb` triplet inside `rgba()` instead.

**Bad:** `background: #00f0ff66;`
**Good:** `background: rgba(var(--neon-cyan-rgb), 0.4);`

## `missing-tier-border` — MAJOR

A capture-stream-style card that omits `:data-tier` and the matching 3px left border. Breaks parity with the sanctioned tier rail pattern.

## `pulse-without-reduced-motion` — MAJOR

Any `animation:` rule that lacks a `@media (prefers-reduced-motion: reduce)` override that disables it.

## `missing-focus-ring` — CRITICAL

Interactive element (`<button>`, `<a>`, `<input>`) without a visible focus indicator. Sanctioned: `focus:ring-2 focus:ring-neon-cyan/60`.

## `shallow-alpine-state` — MINOR

Three or more state vars that always mutate together. Should collapse into one nested object.

**Bad:**

```js
{
  drawerOpen: false,
  drawerLoading: false,
  drawerError: null,
  drawerData: null,
}
```

**Good:**

```js
{
  drawer: { open: false, loading: false, error: null, data: null },
}
```

## `foreign-class-name` — MINOR

Bootstrap (`btn-primary`, `container-fluid`), Material (`mdc-*`), or other foreign framework class names. Theseus is Tailwind-only.

## `missing-prefers-reduced-motion` — MAJOR

Any keyframe animation that lacks a `@media (prefers-reduced-motion: reduce)` override.
