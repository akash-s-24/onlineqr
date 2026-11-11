# Daksha Infinix Living Campus Redesign

## Intent

Replace the current inconsistent, effect-heavy visual system with one professional responsive system across public event pages, registration, and authenticated workspaces. Make event information and registration easy to scan, give light and dark modes distinct layered color identities, and remove the moving space/starfield and particle headline. Keep existing product facts, routes, and workflows.

## Goals

- Give every route a coherent header, type scale, spacing rhythm, surface palette, and control language.
- Use a multi-hue dark environment that feels like a contemporary campus at night, not a single black fill or a space-flight view.
- Retain the 3D CD carousel exactly as it currently behaves and looks. Recolor only its surrounding stage/background to fit the selected theme.
- Remove ordinary button pop, press, liquid, and mechanical-keyboard effects. Use clear static button shapes with color-only hover and strong keyboard focus.
- Replace the current theme toggle with an attractive, accessible appearance panel showing the two modes and their palette previews.
- Keep the site responsive, performant, and usable when reduced motion is enabled.

## Non-goals

- Changing database records, route behavior, registration validation, payment flows, or workspace permissions.
- Replacing event imagery, altering event descriptions, or inventing new promotional claims.
- Rebuilding the Flask app in a new framework.
- Altering the CD carousel's movement, controls, disc treatment, or event-selection behavior.
- Removing ordinary interface functionality or button actions.

## Anti-goals

- No backward-moving stars, space-flight simulation, particle headline, neon glow, or black-only dark background.
- No button bounce, fake keyboard key, compression, ripple, or liquid-fill animation on regular actions.
- No hidden-by-default content that depends on scroll animation to become readable.
- No generic rounded-card grid for every section; use varied editorial section structures and a deliberate reading rhythm.

## Approaches considered

1. **A — Festival Field Guide:** Warm ivory, evergreen, rust, and brass; a campus-program/editorial layout. It is welcoming and distinctive but makes the intended multi-color dark atmosphere less immediate.
2. **B — Living Campus (selected):** Mineral mist and deep ocean/blue-green, with jade and restrained coral. The dark mode gains layered teal, cyan, and muted coral ambient color; the light mode stays clean and readable. This was selected by the user from the two visual mockups because it gives the theme depth without retaining the space visual.
3. **Hybrid palettes:** Use A's light palette with B's dark palette. This is viable but weakens the identity across modes; the user selected B as a complete system.

## Approved direction

**Living Campus.** Use the user's selected B mockup as visual reference: [generated direction board](/Users/akash/.codex/generated_images/01a1c591-0382-7a41-a39c-4681fa16dfe0/exec-a67e46d6-ec61-4d75-a9d8-63265a688695.png). Its campus image is illustrative only and must not be presented as a verified photograph of the actual campus.

### Color and appearance

- Light surfaces: mineral mist `#F2F6F8`, white `#FFFFFF`, pale blue-green `#E2EDF1`.
- Light text: deep blue ink `#172C40`, secondary slate `#516779`.
- Light actions: deep teal `#176E6A`, coral `#D36A50`; muted blue-green for supporting accents.
- Dark base: ocean ink `#101E2C`; raised surface `#192A3A`; secondary surface `#213849`.
- Dark text: warm white `#F2F4EF`; secondary `#B4C2C8`.
- Dark accents: jade/cyan for primary actions and a subdued coral signal.
- The dark background uses a deep ocean base plus overlapping low-opacity cyan, jade, and coral color fields. Animate the color field slowly (roughly 30–45 seconds), without stars or particles. Keep the underlying surface color visible, pause or simplify off-screen, and use a static layered version for reduced-motion preference.
- Category colors remain distinct but controlled; check text/background pairs for WCAG AA.

### Layout and content hierarchy

- Public event page: compact academy navigation; event-first hero with title, dates, key facts, and a single primary registration action; existing CD carousel retained as the signature event browser; category and event details remain easy to find; registration guidance, FAQs, campus/location, coordinators, and footer follow in a deliberate information rhythm.
- The carousel keeps its existing geometry, discs, controls, and animation. Its stage background, outer surface, and surrounding section may use the theme palette.
- Registration: one clear form column on mobile, balanced form/details layout on wider screens, persistent selected-event summary, visibly grouped payment and demo-mode information.
- Admin/member screens: retain all tables, controls, and workflows while adopting the shared typography, surfaces, spacing, navigation, and action states.
- Use a high-character display serif for major page titles and a readable sans-serif for controls, paragraphs, and data. Keep body copy around 65–75 characters per line on wide screens.

### Motion, scroll, and buttons

- Delete the starfield and particle-text animation paths from the public hero.
- Use native scrolling and anchor behavior; no scroll hijack. Reveal only selected sections with a brief opacity/8–12px translate when they enter view, with content visible by default and a reduced-motion fallback.
- Keep the slow ambient dark color-field motion independent of the CD carousel.
- Ordinary buttons have no transform or animated shadow on hover/press. Hover is a subtle color change; click is immediate; focus gets a clear 2–3px theme-colored outline. Do not apply these rules to carousel discs.
- Preserve the carousel's current motion and interaction exactly.

### Appearance panel

- A theme control opens a small polished panel/popover with two large preview choices (Light and Dark), representative palette swatches, selected-state clarity, and an immediate preview.
- Selection persists using the existing `dx-theme` preference and remains compatible with `sda_theme` where required. Update accessible names, `aria-pressed`/selected state, and `theme-color` metadata.
- The panel is keyboard-operable, closes predictably, and does not trap focus unless implemented as a modal dialog.

## Constraints and decisions left to implementation

- Keep the current Flask/Jinja and vanilla CSS/JavaScript stack; use existing routes and supplied content.
- Keep event and organization facts unchanged. Use the existing carousel and images; do not use the generated mockup's illustrative campus artwork in production.
- Implement all colors through semantic theme tokens; remove obsolete visual overrides as they are replaced rather than adding another endless override layer.
- Build a responsive test matrix for 360/390/430px and desktop across light/dark, including event page, carousel stage, registration form, theme panel, and workspace shell.

## Approval

This design is a proposal for review. Implementation starts after the user approves this document.
