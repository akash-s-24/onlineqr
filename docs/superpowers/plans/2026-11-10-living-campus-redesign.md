# Living Campus Website Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved Living Campus visual system across public event and registration pages and authenticated workspaces while preserving existing behavior and the CD carousel.

**Architecture:** Replace the existing accumulating theme overrides with semantic tokens in `daksha-theme.css`, then apply them through the existing Jinja template hierarchy. Public and workspace shells will share accessible theme selection and control styling; page markup receives responsive editorial layouts without changing Flask routes, event data, form fields, or operations. Keep the carousel DOM and animation implementation intact, changing only its surrounding stage palette.

**Tech Stack:** Flask/Jinja templates, existing CSS, vanilla JavaScript, localStorage theme preference, and native browser scrolling.

**Spec:** `docs/superpowers/specs/2026-11-10-daksha-infinix-living-campus-design.md`

## Global Constraints

- Keep every existing route, form field, validation rule, event fact, payment behavior, workspace action, and permission unchanged.
- Preserve the CD carousel's markup, disc treatment, controls, movement, event selection, and behavior; theme its surrounding stage only.
- Use Living Campus palette values from the spec and semantic CSS custom properties for shared theme colors.
- Remove starfield and particle headline effects; remove pop, press, mechanical, and liquid effects from ordinary buttons.
- Keep content visible by default, native scrolling, visible keyboard focus, WCAG AA contrast for text pairs, responsive layouts, and reduced-motion support.
- Do not introduce mockup imagery or unsupported promotional content.

## Review Focus

- Theme choice saved under `dx-theme` and legacy `sda_theme` remains consistent between public and workspace layouts; inspect initial load, switching, and metadata color.
- At narrow widths, header/theme panel, event content, carousel, form, and workspace tables remain usable without clipped controls or horizontal page overflow.
- CD carousel controls and motion work as before in both themes; only the stage environment changes.
- Reduced-motion users see no ambient animation or reveal movement, while all content remains visible.
- Ordinary buttons retain their actions, disabled states, and focus indication after liquid/pop styling and scripts are removed.

---

## File Structure

- `static/css/daksha-theme.css`: replace legacy override accumulation with design tokens, shared surfaces, typography, layout primitives, theme panel, focus, reduced-motion, and ambient background styles.
- `templates/landing_base.html`: public shell navigation/theme-panel integration, shared theme preference logic, and removal of old theme-toggle/particle/liquid script hooks and scroll hijacking.
- `templates/base.html`: authenticated shell theme-panel integration and shared token styling; remove obsolete theme-toggle and liquid-button script hooks.
- `templates/events.html`: event-page hierarchy and responsive sections; remove starfield/particle hero hooks and preserve carousel implementation while recoloring its stage.
- `templates/register.html`: responsive grouped registration/details/payment presentation using existing fields and content.
- `static/css/style.css`: neutralize old candy/pop button movement and unify ordinary control states relied upon by workspace pages.
- `static/css/liquid-button.css`, `static/js/liquid-button.js`: keep the existing carousel control treatment available only for the CD carousel; disable automatic enhancement for ordinary controls.
- `static/js/particletext.js`: delete after its references are removed.
- `templates/admin_dashboard.html`, `templates/member_dashboard.html`, `templates/participants.html`, `templates/members_list.html`, `templates/my_events.html`, `templates/attendance.html`, `templates/certificates.html`, `templates/add_event.html`, `templates/edit_event.html`, `templates/edit_participant.html`, `templates/login.html`, `templates/payment_status.html`, `templates/qr_scanner.html`, and `static/css/dashboard.css`: apply shared surfaces, type, spacing, tables, and responsive navigation without altering controls or workflow.

## Plan

### Task 1: Establish the shared Living Campus token and control layer

**Files:**
- Modify: `static/css/daksha-theme.css`
- Modify: `static/css/style.css`

- [ ] Replace the current theme override pile with semantic light/dark custom properties using approved values: light `#F2F6F8`, `#FFFFFF`, `#E2EDF1`, ink `#172C40`, muted `#516779`, teal `#176E6A`, coral `#D36A50`; dark `#101E2C`, `#192A3A`, `#213849`, text `#F2F4EF`, muted `#B4C2C8`, jade/cyan, subdued coral.
- [ ] Define shared typography, spacing, border, radius, shadow, container-width, and focus-ring tokens; use Fraunces for major titles and existing sans-serif for interface text.
- [ ] Define shared surface, link, input, table, and ordinary button states on the tokens; remove hover/active transforms, animated shadows, key-press offsets, ripple/liquid fills, and pop transitions from ordinary buttons.
- [ ] Add theme-scoped layered dark ambient color fields with a 30–45 second low-opacity cycle; use static layers for `prefers-reduced-motion`, keep the base visible, and include an offscreen pause strategy.
- [ ] Add shared section reveal utility with initial visible state and opt in selected sections only; disable reveal motion for reduced-motion preference.
- [ ] Keep carousel-specific selectors out of global ordinary-button rules; explicitly preserve carousel controls from generic resets.

**Checkpoint:** Shared values are centralized, both themes have distinct layered surfaces, ordinary buttons have no press/pop movement, and carousel selectors are excluded from effect removal.

### Task 2: Implement one accessible appearance panel in both shells

**Files:**
- Modify: `templates/landing_base.html`
- Modify: `templates/base.html`
- Modify: `static/css/daksha-theme.css`

- [ ] Replace sun/moon toggles with a shared appearance trigger and popover offering Light and Dark preview cards, color swatches, selected state, and clear labels in desktop and mobile navigation.
- [ ] Define a single vanilla-JS theme API (`window.setSiteTheme(theme)`) that accepts only `light|dark`, updates `data-theme` and `.dark`, persists both `dx-theme` and `sda_theme`, updates `#themeColorMeta`, updates `aria-pressed`/selected state, and dispatches the existing `sda-theme-changed` event.
- [ ] Make the panel keyboard operable: trigger opens/closes, Escape closes and returns focus, selection applies immediately and closes, outside pointer closes, and focus is not trapped.
- [ ] Update both early theme initialization snippets to accept only known values and set approved theme-color metadata without flashing the wrong palette.
- [ ] Style popover cards and swatches with tokenized focus, selected, and hover states; keep mobile controls reachable from the existing menu.

**Checkpoint:** Public and workspace shells expose consistent theme choice and use the same preference and accessible selected state.

### Task 3: Redesign public event page and atmosphere while retaining the carousel

**Files:**
- Modify: `templates/events.html`
- Modify: `templates/landing_base.html`
- Modify: `static/css/daksha-theme.css`

- [ ] Rework the event hero into an event-first editorial hierarchy with the existing title, date/facts, and registration action; keep supplied content and claims unchanged.
- [ ] Remove `#heroStarfield`, particle headline markup, particle initialization, celestial space background rules, and old hero motion dependencies; apply the new ambient dark color field at the page shell.
- [ ] Improve section rhythm for event discovery, rules/guidance, FAQ, location/contact, and footer using varied editorial layouts rather than repeating one card grid; retain anchors and content.
- [ ] Preserve all `discCascade` markup and JavaScript behavior. Adjust only stage/outer section color, surface, border, and ambient integration for light and dark themes.
- [ ] Remove public-shell smooth-scroll interception and custom scroll hijacking; use native anchor behavior and preserve programmatic navigation actions.
- [ ] Apply selected-section reveal only where it does not hide content or interfere with carousel/form controls; keep content readable before scripts execute.

**Checkpoint:** Carousel controls, lineup selection, and motion remain unchanged; old star/particle hooks are absent; event content/actions remain present.

### Task 4: Redesign registration form presentation

**Files:**
- Modify: `templates/register.html`
- Modify: `static/css/daksha-theme.css`

- [ ] Group existing registration inputs into clearly labeled sections and use one-column mobile layout with a balanced form/details composition at wider widths.
- [ ] Keep selected event, entry fee, guidance, payment instructions, demo mode text, and every existing form control and name unchanged.
- [ ] Style validation, upload, select, payment, and submit states using the shared palette, readable errors, clear focus, and no liquid/pop button effects.
- [ ] Ensure narrow viewports retain readable labels, usable controls, and an accessible selected-event summary.

**Checkpoint:** Form control names and submission target remain unchanged while layout and surfaces follow the tokens.

### Task 5: Apply the shared system to authenticated workspaces

**Files:**
- Modify: `templates/base.html`
- Modify: `static/css/dashboard.css`
- Modify: workspace child templates listed in File Structure only where page-specific layout rules are needed.

- [ ] Restyle workspace navigation, page headers, metrics, forms, filters, tables, dialogs, and action groups with shared type, spacing, surfaces, borders, and theme states.
- [ ] Preserve all workspace controls, table columns, status indicators, actions, permissions, and mobile navigation behavior.
- [ ] Add responsive table treatment appropriate to existing structures (contained horizontal table scrolling where needed) without hiding data or actions.
- [ ] Ensure status/success/warning/error colors remain distinct and legible in both themes.

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

- [ ] Keep the liquid script/style only on the public landing shell for the existing CD carousel controls; remove ordinary-button enhancement selectors and obsolete particle-text asset references.
- [ ] Search all templates and assets for `heroStarfield`, particle-text hooks, `liquid-btn`, and ordinary `pop-btn` press states; remove dead integration paths without changing carousel behavior.
- [ ] Run the project's documented local startup procedure and manually inspect public event, registration, login, admin, and member screens at 360, 390, 430px and desktop in both themes.
- [ ] Manually inspect theme panel keyboard flow, stored preference, theme metadata, focus visibility, reduced-motion rendering, browser console, and ordinary button click behavior.
- [ ] Compare the carousel before/after visually and interactively to confirm disc treatment, geometry, controls, and animation are preserved while stage colors respond to theme.
- [x] Run the Impeccable visual detector; review its findings in the context of the legacy template and shared palette.
- [ ] Capture final light/dark desktop and mobile screenshots and correct remaining verified contrast, clipping, or consistency issues.

**Checkpoint:** No starfield/particle hero or ordinary animated-button integrations remain; both themes are visually coherent and the carousel behavior is preserved.

## Execution Notes

- Work task-by-task in order. Tasks 1 and 2 establish shared contracts consumed by later template work.
- Do not alter routes, backend models, seeded data, forms, payments, or permissions.
- Do not add or run automated tests unless requested; the verification above is manual UI review only.
