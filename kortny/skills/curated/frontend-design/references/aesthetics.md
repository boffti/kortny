# Frontend Aesthetic Guidance

Vendored from anthropics/skills@57546260 under Apache-2.0, adapted for Kortny Slack-first context.

---

## The brief wins — but defaults are traps

AI-generated design clusters around three common looks:
1. Warm cream background (~#F4F1EA) + high-contrast serif display + terracotta accent
2. Near-black background + single bright acid-green or vermilion accent
3. Broadsheet layout with hairline rules, zero border-radius, dense newspaper-like columns

All three are legitimate for some briefs, but they emerge as defaults rather than choices — appearing regardless of subject matter. Where the brief specifies a visual direction, follow it exactly. Where it leaves an axis free, spend that freedom on a choice made for *this specific* brief, not a default.

---

## Ground the design in the subject

Before designing: name one concrete subject, its audience, and the page's single job. If the brief doesn't pin this down, pin it yourself and state your choice.

The subject's own world — its materials, instruments, artifacts, vernacular — is where distinctive choices come from. Build with the brief's real content and subject matter throughout.

---

## Design principles

**The hero is a thesis.** Open with the most characteristic thing in the subject's world — a headline, an image, an animation, a live demo, an interactive moment. A big number with a small label and gradient accent is the template answer; only use it if that is genuinely the best option for this subject.

**Typography carries personality.** Pair display and body faces deliberately — not the same families you would reach for on any other project. Set a clear type scale with intentional weights, widths, and spacing. The type treatment itself should be memorable, not a neutral delivery vehicle.

**Structure is information.** Structural devices — numbering, eyebrows, dividers, labels — should encode something true about the content. Many generic designs use numbered markers (01 / 02 / 03), but this is only appropriate when the content is actually a sequence where order matters. Question every structural device before using it.

**Motion serves the subject.** Where animation helps: page-load sequences, scroll-triggered reveals, hover micro-interactions, ambient atmosphere. An orchestrated moment usually lands harder than scattered effects. Sometimes less is more — extra animation can read as AI-generated.

**Complexity matches vision.** Maximalist directions need elaborate execution; minimal directions need precision in spacing, type, and detail. Elegance is executing the chosen direction well.

---

## Process: brainstorm → plan → critique → build → critique again

**Pass 1 — design plan** (before writing a line of code):

Produce a compact token system:
- **Color**: 4–6 named hex values with their roles
- **Type**: characterful display face (used with restraint) + complementary body face + optional utility face for captions/data
- **Layout**: one-sentence prose description + ASCII wireframe to ideate and compare options
- **Signature**: the single unique element this design will be remembered by — the thing that embodies the brief in an appropriate way

**Pass 1 critique** (before building): if any part of the plan reads like something you would produce for any similar brief rather than *this specific* brief — revise it. Say what changed and why. Only after confirming relative uniqueness should code begin.

**Pass 2** — build, following the revised plan exactly, deriving every color and type decision from the token system.

---

## Restraint and self-critique

Spend boldness in one place. Let the signature element be the one memorable thing; keep everything around it quiet and disciplined. Cut any decoration that doesn't serve the brief.

Build to a quality floor without announcing it: responsive to mobile, visible keyboard focus states, reduced motion respected.

Before finishing: consider Chanel's advice — remove one accessory. What in this design is one element too many?

---

## Writing in design

Words appear in a design for one reason: to make the design easier to understand and use. They are design material, not decoration.

**Write from the user's side.** Name things by what people control and recognize, not by how the system is built. "Manage notifications" not "Configure webhook settings."

**Active voice as default.** A control says exactly what happens when used: "Save changes," not "Submit." Vocabulary stays consistent across a flow — the button that says "Publish" produces a toast that says "Published."

**Failures and empty states direct.** Explain what went wrong and how to fix it. Errors don't apologize and are never vague. An empty screen is an invitation to act — write it that way.

**Register**: plain verbs, sentence case, no filler, tone matched to the brand and audience. One job per element.

---

## CSS specificity caution

When generating CSS: watch for selector conflicts, especially between type-based selectors (`.section`) and element-based ones (`.cta`). This commonly cancels out paddings and margins between sections. Test before shipping.

---

## Delivery for Slack context

When producing HTML mockups for Kortny:
- Upload as a file (via Slack file upload) if the HTML is more than ~30 lines
- Post inline as a code block for small snippets
- Offer both a preview description and the code — let the requester decide whether to render it in a canvas or download it
