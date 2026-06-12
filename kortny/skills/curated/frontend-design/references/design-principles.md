# Frontend design principles

## Spacing

Use a 4px base unit. Prefer multiples: 4, 8, 12, 16, 24, 32, 48, 64.
Never use arbitrary values like 13px or 22px without a documented reason.
Consistent spacing creates visual rhythm — inconsistent spacing destroys it.

## Typography

- Body text: 16px / 1.5 line-height minimum.
- Heading scale: use a ratio (1.25 minor third is safe for UI; 1.333 perfect fourth for marketing).
- Never set body text above 700px wide — readability degrades.
- Limit to 2 typefaces per page. 1 is often enough.

## Color

- Contrast (WCAG AA): 4.5:1 for body text on background; 3:1 for large text (18px+ or 14px bold) and UI components.
- Use CSS custom properties; no raw hex in component CSS.
- Status colors: success = green family, error = red family, warning = amber — don't invent your own.

## Motion

- Transitions: 150-250ms for small UI feedback (button hover, tooltip appear); 300-400ms for panel/modal.
- Easing: `ease-out` for entrances, `ease-in` for exits, `ease-in-out` for repositions.
- No animation that cannot be disabled via `prefers-reduced-motion`.

## Accessibility

- Every focusable element must have a visible focus ring (2px solid, 2px offset, contrasting color).
- Images require `alt` text; decorative images use `alt=""`.
- Form inputs require an associated `<label>`.
- Modals must trap focus and restore it on close.
- ARIA roles only when semantic HTML cannot achieve the same result.

## Component checklist

Before shipping any component:
- [ ] Keyboard navigable
- [ ] Screen-reader tested (VoiceOver or NVDA)
- [ ] Mobile viewport breakpoint handled
- [ ] Dark mode variant (if the product has one)
- [ ] Error and empty states designed
