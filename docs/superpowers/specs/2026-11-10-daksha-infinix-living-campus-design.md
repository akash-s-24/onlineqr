# Daksha Infinix Living Campus Redesign

## Intent

Replace the current inconsistent, effect-heavy visual system with one professional responsive system across public event pages, registration, and authenticated workspaces. Make event information and registration easy to scan, give light and dark modes distinct monochrome layered identities, and remove the moving space/starfield and particle headline. Keep existing product facts, routes, and workflows.

## Goals

- Give every route a coherent header, type scale, spacing rhythm, surface palette, and control language.
- Use a layered black/charcoal dark environment with grayscale depth and no space-flight or starfield treatment.
- Retain the 3D CD carousel exactly as it currently behaves and looks. Recolor only its surrounding stage/background to fit the selected theme.
- Use a restrained theme-aware candy-style surface and brief mechanical press only for event-card Rules and Contact controls inside the Events grid. Keep Contact Us controls and all other buttons unchanged.
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
- Avoid changing button animations outside the Events section; its Rules and Contact actions use a short mechanical press without a bounce, ripple, liquid fill, or keyboard-key appearance.
- No hidden-by-default content that depends on scroll animation to become readable.
- No generic rounded-card grid for every section; use varied editorial section structures and a deliberate reading rhythm.

## Approaches considered (initial exploration)

1. **A — Festival Field Guide:** Warm ivory, evergreen, rust, and brass; a campus-program/editorial layout. It is welcoming and distinctive but makes the intended multi-color dark atmosphere less immediate.
2. **B — Living Campus (initial selection):** Mineral mist and deep ocean/blue-green, with jade and restrained coral. This was the initial direction before the user updated the palette to monochrome.
3. **Hybrid palettes:** Use A's light palette with B's dark palette. This is viable but weakens the identity across modes.

## Initial approved direction (superseded)

**Living Campus.** The initial selected B mockup was used as a reference: [generated direction board](/Users/akash/.codex/generated_images/01a1c591-0382-7a41-a39c-4681fa16dfe0/exec-a67e46d6-ec61-4d75-a9d8-63265a688695.png). Its campus image is illustrative only and must not be presented as a verified photograph of the actual campus.

### Color and appearance (initial direction, superseded)

The original multicolor Living Campus proposal is historical context only. The current palette is specified in the user direction update below.

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
- Only Rules and Contact actions in the Events section use the restrained theme-aware candy surface and mechanical press. Contact Us, other buttons, and carousel controls remain unchanged. Keep a clear keyboard focus outline on the redesigned controls.
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


## User Direction Update — 2026-11-13

This update supersedes the Living Campus color direction above. Use a monochrome white theme and a layered black theme throughout the website. The dark theme may use subtle grayscale gradients for depth; remove the teal, blue, coral, and starfield colors. Update the appearance panel to show monochrome theme previews.

Give only the event-grid Rules and Contact buttons a polished theme-aware candy surface and short mechanical press animation. Keep Contact Us and every other button unchanged. Preserve the CD carousel controls and animation. Remove the outdated suffix from all institution labels; use “Affiliated to Bengaluru University and approved by AICTE” and show “Degree Programmes: BCA · MCA.”

## Active User Direction

Use a white theme and a black theme with subtle layered depth. Apply the theme-aware mechanical candy press only to the Events-section Rules and Contact controls. Do not change Contact Us buttons or other buttons. Preserve the CD carousel, including its controls and motion; only its surrounding/background colors may follow the theme. Use “Affiliated to Bengaluru University and approved by AICTE.” under the college name, remove the outdated college suffix, and show “Degree Programmes: BCA · MCA” in the address/affiliation layout.
