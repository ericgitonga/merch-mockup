# Merch Mockup

Upload a photograph, add optional top/bottom text labels, and choose a text
colour and t-shirt colour to generate a print-ready TIFF (black background),
a transparent PNG, and a t-shirt mockup JPG.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Opens on `http://127.0.0.1:5000`.

## Testing

A Playwright-based E2E smoke suite lives in `e2e/` — the upload/generate
golden path, validation error paths, and token-based route 404s. It's gated
in CI on every PR to `main` (`.github/workflows/e2e.yml`) and runs against a
real gunicorn server, the same entrypoint used in `render.yaml`.

Run it locally:

```bash
gunicorn app:app --bind 0.0.0.0:5000 &   # in one terminal
conda run -n ds python e2e/run.py        # in another
```

## Deployment

Deployed to [Render](https://render.com) as a Python (Flask + gunicorn) web service.
Render redeploys automatically on every push to `main`.
