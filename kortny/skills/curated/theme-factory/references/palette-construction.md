# Palette construction method

## Starting from a brand color

1. **Fix the primary hue** from the brand color.
2. **Generate shades**: use HSL. Keep hue constant; vary lightness from 20% (darkest) to 90% (lightest) in steps. For a 2-shade primary: `primary-600` (default) and `primary-400` (light/hover).
3. **Pick a secondary hue**: rotate 120° on the color wheel for strong contrast; 30°-60° for analogous harmony. Apply same shade generation.
4. **Neutral scale** (6 steps):
   - `neutral-900` (#111 area): body text
   - `neutral-700` (#444 area): secondary text
   - `neutral-500` (#888 area): placeholder / muted
   - `neutral-300` (#ccc area): borders
   - `neutral-100` (#f5 area): card backgrounds
   - `neutral-50` (#fafafa area): page background

## Semantic colors

Always include:
- `color-success`: a green in the 120°-150° hue range (lightness 35-45% for AA contrast on white)
- `color-warning`: amber (40°-55° hue, lightness 35-45%)
- `color-error`: red (0°-15° hue, lightness 35-45%)
- `color-info`: blue (210°-230° hue, lightness 35-45%)

## Contrast verification

For each text color on its intended background, calculate contrast ratio:
- Body text on background: must be ≥ 4.5:1
- Large text (≥18px or ≥14px bold): must be ≥ 3:1
- UI components (buttons, inputs borders): must be ≥ 3:1

Use the formula: `contrast = (L1 + 0.05) / (L2 + 0.05)` where L1 > L2, relative luminance per WCAG 2.1.

## CSS output format

```css
:root {
  --color-primary-600: #1a56db;
  --color-primary-400: #4d80e4;
  --color-secondary-600: #7e3af2;
  --color-secondary-400: #a474f6;
  --color-neutral-900: #111827;
  --color-neutral-700: #374151;
  --color-neutral-500: #6b7280;
  --color-neutral-300: #d1d5db;
  --color-neutral-100: #f3f4f6;
  --color-neutral-50:  #f9fafb;
  --color-success:     #057a55;
  --color-warning:     #c27803;
  --color-error:       #c81e1e;
  --color-info:        #1c64f2;
}
```
