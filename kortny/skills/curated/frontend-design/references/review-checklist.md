# Frontend design review checklist

For each dimension: state the finding (pass / warn / fail), the specific instance, and the one-line fix.

## Visual clarity

- [ ] Hierarchy: can you tell within 3 seconds what the primary action is?
- [ ] Whitespace: is there breathing room between sections?
- [ ] Typography: is body text readable at the intended viewport?
- [ ] Color: does the palette convey meaning consistently?

## Accessibility

- [ ] Contrast: all text meets WCAG AA (4.5:1 body, 3:1 large/UI)
- [ ] Focus states: all interactive elements have visible focus indicators
- [ ] Alt text: images present and meaningful (or `alt=""` for decorative)
- [ ] Motion: no animation without `prefers-reduced-motion` fallback

## Code quality

- [ ] No inline styles (except dynamic values)
- [ ] CSS custom properties used for theme values
- [ ] No magic numbers (undocumented spacing/sizing values)
- [ ] Semantic HTML (buttons are `<button>`, links are `<a href>`)

## Responsiveness

- [ ] Tested at 320px, 768px, 1280px minimum
- [ ] Images do not overflow their containers
- [ ] Text does not overlap at any breakpoint

## States

- [ ] Hover state defined for interactive elements
- [ ] Active/pressed state defined
- [ ] Focus state defined
- [ ] Disabled state defined (and not just `opacity: 0.5`)
- [ ] Error state defined for form inputs
- [ ] Empty state designed for data-dependent views
- [ ] Loading state designed (skeleton or spinner, not blank)
