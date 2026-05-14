# Sanctioned Component Patterns

These are the canonical Theseus cyberpunk components. Look-alike surfaces (cards, chips, drawers, inputs) MUST match the corresponding pattern or be flagged as drift.

## Capture Stream Card (Tier-Colored Border)

Every capture-stream `<article>` carries `:data-tier="note.tier"` and a 3px neon left border driven by the tier. Sanctioned tiers: `doctrine` → cyan, `intelligence` → magenta, `pursuit` → amber.

```css
#vault-capture-stream article[data-tier="doctrine"] {
  border-left: 3px solid var(--neon-cyan);
}
#vault-capture-stream article[data-tier="intelligence"] {
  border-left: 3px solid var(--neon-magenta);
}
#vault-capture-stream article[data-tier="pursuit"] {
  border-left: 3px solid var(--neon-amber);
}
```

**Anti-pattern:** card on a tier-aware surface that omits `:data-tier` and the matching border rule.

## In-Flight Pulse

Live submit / processing buttons pulse cyan while the request is in flight. Use the `capture-submit-pulse` class with the matching keyframes.

```css
.capture-submit-pulse {
  animation: capture-submit-pulse-anim 1.4s ease-in-out infinite;
}
@keyframes capture-submit-pulse-anim {
  0%, 100% { box-shadow: 0 0 0 0 rgba(var(--neon-cyan-rgb), 0.45); }
  50%       { box-shadow: 0 0 0 8px rgba(var(--neon-cyan-rgb), 0.05); }
}
@media (prefers-reduced-motion: reduce) {
  .capture-submit-pulse { animation: none; }
}
```

**Anti-pattern:** pulse animation without a `prefers-reduced-motion` override.

## Three-State Status Dot

Notes carry a status dot that signals `raw` (amber), `polished` (cyan), `evergreen` (lime). Same vocabulary across the app.

## Neon Focus Ring

Every interactive element gets a visible cyan focus ring. Sanctioned utility:

```html
<button class="focus:outline-none focus:ring-2 focus:ring-neon-cyan/60">…</button>
```

Or in CSS: `box-shadow: var(--shadow-glow);` on `:focus-visible`.

## Drawer Slide-In

Side panels slide from the right at 70vw with a backdrop click + Escape dismiss. The drawer claims the canonical id of any chart/canvas it hosts so helpers don't double-target.

## Mono Placeholder

Inputs use a monospace placeholder for that "terminal" feel:

```css
#vault-capture-input::placeholder {
  font-family: ui-monospace, SFMono-Regular, monospace;
  color: var(--text-500);
}
```

## Caret Color

Inputs use the brand cyan caret:

```css
#vault-capture-input { caret-color: var(--neon-cyan); }
```
