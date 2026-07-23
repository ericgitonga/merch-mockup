# Changelog

All notable changes to this project are documented here. Versioning follows
[Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH. This project is
pre-1.0 (initial development) — the major version stays at `0` until a stable,
production-ready release is declared. MINOR bumps cover new features and
user-facing changes; PATCH bumps cover fixes, docs, and housekeeping.

## [0.1.1] - 2026-07-23
### Changed
- Cards, buttons, form fields, and preview images now have a slight
  `border-radius` (6px) instead of hard 0px corners, softening the theme a
  little. (closes #2)
- `.gitignore` now excludes AI-assistant instruction files (`CLAUDE.md`,
  `AGENTS.md`, `SKILL.md`, `.claude/`, `.agents/`) — living local docs, not
  tracked in the repo itself, matching the convention already used in
  `umoja-voices`.

tag: `v0.1.1`

## [0.1.0] - 2026-07-23
### Added
- Ported the photo/text/colour -> TIFF/PNG/mockup-JPG design generator from a
  Gradio prototype to a Flask + gunicorn app, matching the stack used by
  `extras/Career Transition`. Gradio had proven unreliable to deploy on
  Render, which motivated the port.
- Restyled the app to match a WooCommerce-style storefront reference: black
  top bar, centered white title band, white content cards, black buttons,
  blue link accents.
- Bundled the fonts the pipeline depends on under `Assets/` instead of an
  absolute local path. (closes #1)

tag: `v0.1.0`

---
