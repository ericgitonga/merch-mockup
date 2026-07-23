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

## Deployment

Deployed to [Render](https://render.com) as a Python (Flask + gunicorn) web service.
Render redeploys automatically on every push to `main` — no CI/CD workflow required.
