# Living Campus Website Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the user-directed monochrome visual system across public event and registration pages and authenticated workspaces while preserving existing behavior and the CD carousel.

**Architecture:** Replace the existing accumulating theme overrides with semantic tokens in `daksha-theme.css`, then apply them through the existing Jinja template hierarchy. Public and workspace shells will share accessible theme selection and control styling; page markup receives responsive editorial layouts without changing Flask routes, event data, form fields, or operations. Keep the carousel DOM and animation implementation intact, changing only its surrounding stage palette.

**Tech Stack:** Flask/Jinja templates, existing CSS, vanilla JavaScript, localStorage theme preference, and native browser scrolling.

**Spec:** `docs/superpowers/specs/2026-11-10-daksha-infinix-living-campus-design.md`

## Global Constraints

- Keep every existing route, form field, validation rule, event fact, payment behavior, workspace action, and permission unchanged.
- Preserve the CD carousel's markup, disc treatment, controls, movement, event selection, and behavior; theme its surrounding stage only.
- Use monochrome white/black palette values and semantic CSS custom properties for shared theme colors.
- Remove starfield and particle headline effects. Apply a theme-aware candy mechanical press only to event-card Rules and Contact controls inside the Events grid. Leave Contact Us controls and other buttons unchanged.
- Keep content visible by default, native scrolling, visible keyboard focus, WCAG AA contrast for text pairs, responsive layouts, and reduced-motion support.
- Do not introduce mockup imagery or unsupported promotional content.

## Review Focus

- Theme choice saved under `dx-theme` and legacy `sda_theme` remains consistent between public and workspace layouts; inspect initial load, switching, and metadata color.
- At narrow widths, header/theme panel, event content, carousel, form, and workspace tables remain usable without clipped controls or horizontal page overflow.
- CD carousel controls and motion work as before in both themes; only the stage environment changes.
- Reduced-motion users see no ambient animation or reveal movement, while all content remains visible.
- Only Events-section Rules/Contact controls use the new candy mechanical press; all other buttons, including Contact Us and carousel navigation and action controls, retain their existing behavior.

---

## File Structure

- `static/css/daksha-theme.css`: replace legacy override accumulation with design tokens, shared surfaces, typography, layout primitives, theme panel, focus, reduced-motion, and ambient background styles.
- `templates/landing_base.html`: public shell navigation/theme-panel integration, shared theme preference logic, and removal of old theme-toggle/particle/liquid script hooks and scroll hijacking.
- `templates/base.html`: authenticated shell theme-panel integration and shared token styling; remove obsolete theme-toggle and liquid-button script hooks.
- `templates/events.html`: event-page hierarchy and responsive sections; remove starfield/particle hero hooks and preserve carousel implementation while recoloring its stage.
- `templates/register.html`: responsive grouped registration/details/payment presentation using existing fields and content.
- `static/css/style.css`: retain existing button motion outside the requested Events controls while keeping shared tokens compatible.
- `static/css/liquid-button.css`, `static/js/liquid-button.js`: exclude the four redesigned Events Rules/Contact controls from liquid motion while preserving existing behavior elsewhere.
- `static/js/particletext.js`: delete after its references are removed.
- `templates/admin_dashboard.html`, `templates/member_dashboard.html`, `templates/participants.html`, `templates/members_list.html`, `templates/my_events.html`, `templates/attendance.html`, `templates/certificates.html`, `templates/add_event.html`, `templates/edit_event.html`, `templates/edit_participant.html`, `templates/login.html`, `templates/payment_status.html`, `templates/qr_scanner.html`, and `static/css/dashboard.css`: apply shared surfaces, type, spacing, tables, and responsive navigation without altering controls or workflow.

## Plan

### Task 1: Establish the shared monochrome token and control layer

**Files:**
- Modify: `static/css/daksha-theme.css`
- Modify: `static/css/style.css`

- [x] Replace the current theme override pile with semantic white/black custom properties: white `#FFFFFF`, gray `#F5F5F5`, ink `#111111`; black `#080808`, raised surfaces `#151515`/`#1D1D1D`, white text `#FAFAFA`.
- [x] Define shared typography, spacing, border, radius, shadow, container-width, and focus-ring tokens; use Fraunces for major titles and existing sans-serif for interface text.
- [x] Define shared surface, link, input, and table states on the tokens; give only Events-section Rules and Contact controls a theme-aware candy mechanical press.
- [x] Add layered monochrome fields to both themes and a subtle hero atmosphere; use static layers for reduced-motion users.
- [x] Add shared section reveal utility with initial visible state and opt in selected sections only; disable reveal motion for reduced-motion preference.
- [x] Scope the mechanical press to Events-section Rules/Contact controls; leave carousel controls and all other button interactions unchanged.

**Checkpoint:** Shared white/black values are centralized, both themes have distinct layered surfaces, and only Events-section Rules/Contact controls receive the new mechanical press.

### Task 2: Implement one accessible appearance panel in both shells

**Files:**
- Modify: `templates/landing_base.html`
- Modify: `templates/base.html`
- Modify: `static/css/daksha-theme.css`

- [x] Replace sun/moon toggles with a shared appearance trigger and popover offering Light and Dark preview cards, color swatches, selected state, and clear labels in desktop and mobile navigation.
- [x] Define the vanilla-JS theme API (`window.setSiteTheme(theme)`) in both shells; it accepts only `light|dark`, updates `data-theme` and `.dark`, persists both `dx-theme` and `sda_theme`, updates `#themeColorMeta`, updates `aria-pressed`/selected state, and dispatches the existing `sda-theme-changed` event.
- [x] Make the panel keyboard operable: trigger opens/closes, Escape closes and returns focus, selection applies immediately and closes, outside pointer closes, and focus is not trapped.
- [x] Update both early theme initialization snippets to accept only known values and set approved theme-color metadata without flashing the wrong palette.
- [x] Style popover cards and swatches with tokenized focus, selected, and hover states; keep mobile controls reachable from the existing menu.

**Checkpoint:** Public and workspace shells expose consistent theme choice and use the same preference and accessible selected state.

### Task 3: Redesign public event page and atmosphere while retaining the carousel

**Files:**
- Modify: `templates/events.html`
- Modify: `templates/landing_base.html`
- Modify: `static/css/daksha-theme.css`

- [x] Rework the event hero into an event-first editorial hierarchy with the existing title, date/facts, and registration action; remove forced subtitle line breaks for natural responsive wrapping.
- [x] Remove `#heroStarfield`, particle headline markup, particle initialization, celestial space background rules, and old hero motion dependencies; apply the new ambient dark color field at the page shell.
- [x] Improve section rhythm for event discovery, rules/guidance, FAQ, location/contact, and footer using their existing distinct layouts plus alternating monochrome surfaces; retain anchors and content.
- [x] Preserve all `discCascade` markup and JavaScript behavior. Adjust only stage/outer section color, surface, border, and ambient integration for light and dark themes.
- [x] Remove public-shell smooth-scroll interception and custom scroll hijacking; use native anchor behavior and preserve programmatic navigation actions.
- [x] Apply a mobile-first event-card reveal only where it does not hide content or interfere with carousel/form controls; keep content readable before scripts execute.

**Checkpoint:** Carousel controls, lineup selection, and motion remain unchanged; old star/particle hooks are absent; event content/actions remain present.

### Task 4: Redesign registration form presentation

**Files:**
- Modify: `templates/register.html`
- Modify: `static/css/daksha-theme.css`

- [x] Group existing registration inputs into clearly labeled sections and use one-column mobile layout with a balanced form/details composition at wider widths.
- [x] Keep selected event, entry fee, guidance, payment instructions, demo mode text, and every existing form control and name unchanged.
- [x] Style validation, upload, select, payment, and submit states using the shared palette, readable errors, clear focus, and no liquid/pop button effects.
- [x] Ensure narrow viewports retain readable labels, usable controls, and an accessible selected-event summary.

**Checkpoint:** Form control names and submission target remain unchanged while layout and surfaces follow the tokens.

### Task 5: Apply the shared system to authenticated workspaces

**Files:**
- Modify: `templates/base.html`
- Modify: `static/css/dashboard.css`
- Modify: workspace child templates listed in File Structure only where page-specific layout rules are needed.

- [x] Restyle workspace navigation, page headers, metrics, forms, filters, tables, dialogs, and action groups with shared type, spacing, surfaces, borders, and theme states.
- [x] Preserve all workspace controls, table columns, status indicators, actions, permissions, and mobile navigation behavior.
- [x] Add responsive table treatment appropriate to existing structures (contained horizontal table scrolling where needed) without hiding data or actions.
- [x] Ensure status/success/warning/error colors remain distinct and legible in both themes.

**Checkpoint:** Admin and member workspaces use both palettes consistently and every existing action remains visible and operable.

### Task 6: Retire unused animation integrations and finish visual review

**Files:**
- Modify: `templates/landing_base.html`
- Modify: `templates/base.html`
- Modify: `templates/events.html`
- Modify: `templates/register.html`
- Modify: `static/css/liquid-button.css`
- Modify: `static/js/liquid-button.js`
- Delete only after confirming no references remain: `static/js/particletext.js`

- [x] Keep legacy liquid motion on non-target Rules/Contact controls; remove liquid enhancement from the four redesigned Events-section controls and remove obsolete particle-text asset references.
- [x] Search templates and assets for `heroStarfield`, particle-text hooks, `liquid-btn`, and ordinary `pop-btn` press states; remove dead integration paths without changing carousel behavior.
- [ ] Run the project's documented local startup procedure and manually inspect public event, registration, login, admin, and member screens at 360, 390, 430px and desktop in both themes.
- [ ] Manually inspect theme panel keyboard flow, stored preference, theme metadata, focus visibility, reduced-motion rendering, browser console, and the four redesigned Events button interactions.
- [ ] Compare the carousel before/after visually and interactively to confirm disc treatment, geometry, controls, and animation are preserved while stage colors respond to theme.
- [x] Run the Impeccable visual detector once; Jinja-generated stylesheet links were not resolved, so findings remain source hints rather than computed page results.
- [ ] Capture final light/dark desktop and mobile screenshots and correct remaining verified contrast, clipping, or consistency issues.

**Checkpoint:** No starfield/particle hero remains; both themes are monochrome, only the targeted Events-section controls use the new mechanical press, and the carousel is preserved.

## Execution Notes

- Work task-by-task in order. Tasks 1 and 2 establish shared contracts consumed by later template work.
- Do not alter routes, backend models, seeded data, forms, payments, or permissions.
- Do not add or run automated tests unless requested; the verification above is manual UI review only.


## User Direction Update — 2026-11-13

The user refined the approved direction after the initial Living Campus brief. This update takes precedence over earlier color and button wording:

- Use monochrome white and black themes across shared site surfaces; remove teal, blue, coral, and starfield color treatments. Keep subtle layered grayscale gradients so the dark theme has depth.
- Apply the theme-aware candy-style mechanical press only to the event-card Rules and Contact controls inside the Events grid. Leave Contact Us controls, all other buttons, and CD carousel controls unchanged.
- Keep the appearance panel swatches monochrome and preview the actual theme surfaces.
- Remove the outdated suffix from all institution labels and use “Affiliated to Bengaluru University and approved by AICTE.” Include “Degree Programmes: BCA · MCA.”

## Active User Direction

Use a white theme and a black theme with subtle layered depth. Apply the theme-aware mechanical candy press only to the Events-section Rules and Contact controls. Do not change Contact Us buttons or other buttons. Preserve the CD carousel, including its controls and motion; only its surrounding/background colors may follow the theme. Use “Affiliated to Bengaluru University and approved by AICTE.” under the college name, remove the outdated college suffix, and show “Degree Programmes: BCA · MCA” in the address/affiliation layout.
