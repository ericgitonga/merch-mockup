# Merch Mockup

Upload a photograph, add optional top/bottom text labels, and choose a text
colour and t-shirt colour to generate a print-ready TIFF (black background),
a transparent PNG, and a t-shirt mockup JPG.

## Architecture

Mostly a single Python/Flask app (`app.py`), plus one small Node.js
Vercel Function (`api/blob-upload.ts`) that mints presigned upload URLs so
photos go straight from the browser to Vercel Blob storage — Vercel
Functions cap request bodies at 4.5MB, which phone photos routinely exceed.
The Flask app itself is stateless: generated files are written to and read
back from Blob rather than local disk, since Vercel Functions give no
guarantee that two separate requests land on the same instance. See
`storage.py` and issue #7 for the full write-up.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Opens on `http://127.0.0.1:5000`. Needs `BLOB_READ_WRITE_TOKEN` in the
environment (pull it with `vercel env pull .env.local` once linked to the
Vercel project) — the upload endpoint (`api/blob-upload.ts`) only runs on
Vercel, so exercising the full upload flow locally means either deploying a
Preview or standing up `vercel dev` yourself.

## Testing

A Playwright-based E2E smoke suite lives in `e2e/` — the upload/generate
golden path, validation error paths, and token-based result handling. It's
gated in CI on every PR to `main` (`.github/workflows/e2e.yml`), which
deploys the PR to a real Vercel Preview and runs the suite against it —
this app's mixed Python + Node Functions and Blob dependency aren't
something a local dev server can faithfully stand in for.

Run it locally against any deployed Preview or Production URL:

```bash
BASE_URL=https://<some-deployment>.vercel.app \
VERCEL_BYPASS_SECRET=<automation bypass secret, if the deployment needs it> \
conda run -n ds python e2e/run.py
```

## Deployment

Deployed to [Vercel](https://vercel.com) (project `egm2/merch-mockup`).
Every PR gets an automatic Preview deployment; merging to `main` promotes
to production. Needs `SECRET_KEY` and `BLOB_READ_WRITE_TOKEN` set as
project environment variables (the latter is auto-provided once a Blob
store is attached to the project).
