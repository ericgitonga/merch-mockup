# Changelog

All notable changes to this project are documented here. Versioning follows
[Semantic Versioning](https://semver.org): MAJOR.MINOR.PATCH. This project is
pre-1.0 (initial development) — the major version stays at `0` until a stable,
production-ready release is declared. MINOR bumps cover new features and
user-facing changes; PATCH bumps cover fixes, docs, and housekeeping.

## [0.4.1] - 2026-07-23
### Fixed
- `/generate` no longer raises an unhandled exception (bare 500) on a
  non-image upload or one that trips Pillow's decompression-bomb guard —
  the whole decode/compose block is now caught and routed through the
  existing `_bounce()` error path.
### Added
- `api/blob-cleanup.ts`, a scheduled (daily, via Vercel Cron) Node Function
  that deletes anything under `uploads/` or `results/` older than 24h.
  Nothing previously deleted generated files or abandoned uploads, so Blob
  storage grew without bound. Guarded by `CRON_SECRET`.
- `package-lock.json` committed for the Node side (`@vercel/blob`) —
  previously only a floating `^2.6.1` range with no lockfile, so builds
  weren't reproducible.
### Changed
- Added Vercel Firewall rate-limit rule covering both `POST /generate` and
  `POST /api/blob-upload` (30 req/60s per IP) — `flask-limiter`'s in-memory
  counters don't reliably survive Vercel's stateless per-invocation Functions,
  and `api/blob-upload.ts` (a separate Node Function) had no throttling of
  any kind. Staged in log-only mode pending traffic review before enforcing.
- (closes #14)

## [0.4.0] - 2026-07-23
### Changed
- Results page now offers a single "Download design" button instead of
  three separate TIFF/PNG/mockup links. A new `/download/<token>` route
  fetches all three files from Blob and zips them in memory
  (`{slug}.tiff`, `{slug}.png`, `{slug}_mockup.jpg`) rather than linking
  straight to each blob's `downloadUrl`.
- `e2e/test_generate.py` updated to assert the single button and unzip the
  response to check its contents. (closes #10)

tag: `v0.4.0`

## [0.3.0] - 2026-07-23
### Changed
- Moved the deploy target from Render to Vercel (Render needs a paid plan
  for another service on this account) — `render.yaml` removed, `vercel.json`
  added declaring the Flask app and the new Node upload Function as separate
  services with routing rewrites, `.python-version` bumped 3.11.9 -> 3.12
  (Vercel doesn't offer 3.11).
- `app.py` no longer writes generated files to local disk: `/generate` and
  `/result/<token>` now read/write Vercel Blob directly via the new
  `storage.py` (a thin `requests`-based wrapper over Blob's plain REST API).
  Vercel Functions give no guarantee that two separate requests land on the
  same instance, so local-disk hand-off across requests was never going to
  work in production. `/preview/<token>/<kind>` and `/download/<token>/<kind>`
  are gone — the result page links directly to Blob URLs instead of
  proxying through Flask.
- Photo upload no longer goes through Flask's own request body at all: a new
  Node.js Function (`api/blob-upload.ts`, the one non-Python file in this
  project) mints a presigned Blob upload URL, and the browser (see
  `static/upload.js`) PUTs the file directly to Blob storage, bypassing
  Vercel's 4.5MB Function body cap entirely — matches how `umoja-voices`
  handles its own large uploads (client-direct-to-storage), adapted from
  Supabase Storage's signed-URL flow to Vercel Blob's.
- `e2e/` reworked for the new upload flow and Blob-URL-based assertions;
  `.github/workflows/e2e.yml` now deploys the PR to a real Vercel Preview
  and runs the suite against it (`vercel dev` and a hand-run local server
  can't faithfully stand in for this app's mixed Python + Node Functions and
  Blob dependency — confirmed directly when a CSP bug silently broke the
  upload JS in a way only a real deployment surfaced).
- Content-Security-Policy's `connect-src` widened to allow the presigned
  Blob PUT (issued on `vercel.com`, not `blob.vercel-storage.com`) and the
  public Blob read host.
- See issue #7 for the full architecture discussion (why Vercel, why Blob,
  why one Node Function, what was tried and rejected).

tag: `v0.3.0`

## [0.2.0] - 2026-07-23
### Added
- Playwright-based E2E smoke suite in `e2e/` covering the upload/generate
  golden path, validation error paths (missing name, disallowed file
  extension), and token-based route 404s — mirroring the pattern used in
  `umoja-voices`, simplified since this app has no auth/database.
- `.github/workflows/e2e.yml` gates every PR to `main` on the suite,
  running it against a real gunicorn server (the same entrypoint used in
  `render.yaml`). (closes #5)

tag: `v0.2.0`

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
