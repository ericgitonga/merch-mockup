"""
Flask app for the Insect Design Generator.

Upload a photo, add optional top/bottom text labels, pick a text colour and
a t-shirt colour, and get back a print-ready TIFF (black background), a
transparent PNG, and a t-shirt mockup JPG.

Ported from a Gradio prototype after Gradio proved unreliable to deploy on
Render — the image-processing pipeline below (crop/compose/mockup) is
unchanged from that prototype. Originally deployed with local-disk storage
for Render; moved to Vercel + Vercel Blob (see storage.py and
api/blob-upload.ts) because Vercel Functions are stateless per-invocation —
there's no guarantee GET /result/<token> lands on the same instance that
wrote files during POST /generate — and because Vercel Functions cap request
bodies at 4.5MB, so the photo upload itself goes straight from the browser
to Blob (bypassing this app entirely) rather than through a multipart POST
here. See issue #7 for the full architecture discussion.
"""

import io
import json
import os
import re
import secrets
import tempfile
import uuid
import warnings
import zipfile
from pathlib import Path

from flask import (
    Flask, Response, abort, flash, redirect, render_template,
    request, url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from PIL import Image, ImageDraw, ImageFont

import storage

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"
TOP_FONT = ASSETS_DIR / "DancingScript-Bold.ttf"
BOT_FONT = ASSETS_DIR / "Kalam-Bold.ttf"

TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

app = Flask(__name__)
APP_VERSION = (BASE_DIR / "VERSION").read_text().strip()

# ── Secret key ─────────────────────────────────────────────────────────────
# On Vercel, SECRET_KEY is set as a project environment variable. Locally, if
# absent, auto-generate one so development is frictionless — the trade-off is
# CSRF tokens invalidate on every restart, which is fine in dev.
_secret = os.environ.get("SECRET_KEY", "")
if not _secret:
    _secret = secrets.token_hex(32)
    warnings.warn(
        "SECRET_KEY not set — using a randomly generated key. "
        "CSRF tokens will be invalidated on restart. "
        "Set SECRET_KEY in your environment (or Vercel project settings) "
        "for production.",
        stacklevel=1,
    )
app.config["SECRET_KEY"] = _secret
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # form fields + a blob URL, not the photo itself

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
)

W, H = 2400, 2900   # design canvas

TEXT_COLOURS = {
    "White":  {"rgb": (255, 255, 255), "shadow": (40,  40,  40)},
    "Black":  {"rgb": (0,   0,   0),   "shadow": (180, 180, 180)},
    "Red":    {"rgb": (220, 30,  30),  "shadow": (80,  0,   0)},
    "Blue":   {"rgb": (30,  100, 220), "shadow": (0,   30,  80)},
    "Green":  {"rgb": (30,  180, 60),  "shadow": (0,   60,  10)},
    "Yellow": {"rgb": (240, 210, 20),  "shadow": (80,  60,  0)},
}

SHIRT_COLOURS = {
    "Black":              "#000000",
    "White":              "#FFFFFF",
    "Deep Navy":          "#0F0F2D",
    "Slate Gray":         "#707070",
    "Coral / Red-Orange": "#FF452B",
    "Mustard Yellow":     "#E5A93B",
    "Deep Plum":          "#7D1B4E",
    "Bright Orange":      "#FFA11A",
    "Terracotta":         "#A46B55",
    "Forest Green":       "#38662B",
    "Crimson Red":        "#CE1A1A",
    "Lime Green":         "#4CD337",
    "Alabaster / Beige":  "#EAE2C8",
    "Khaki / Tan":        "#C1AD8F",
}

# ── T-shirt silhouette (1000 × 1150 canvas) ──────────────────────────────────
MW, MH    = 1000, 1150
MOCKUP_BG = (228, 228, 228)

SHIRT_PTS = [
    (400, 162),   # left collar
    (265, 143),   # left shoulder
    ( 82, 232),   # left sleeve outer-top
    ( 97, 368),   # left sleeve outer-bottom
    (265, 390),   # left underarm
    (240, 1050),  # bottom-left hem
    (760, 1050),  # bottom-right hem
    (735, 390),   # right underarm
    (903, 368),   # right sleeve outer-bottom
    (918, 232),   # right sleeve outer-top
    (735, 143),   # right shoulder
    (600, 162),   # right collar
]
NECK    = dict(cx=500, cy=162, rx=108, ry=62)
CHEST_W = 375
CHEST_Y = 280


# ── Layout helper ─────────────────────────────────────────────────────────────

def _get_layout(top_text, bottom_text):
    """Return (px, py, pw) — photo size and position on the design canvas."""
    has_top = bool(top_text.strip())
    has_bot = bool(bottom_text.strip())

    if has_top and has_bot:
        pw = int(W * 0.80)
        py = int(H * 0.18)
    elif has_top:
        pw = int(W * 0.80)
        py = int(H * 0.18)
    elif has_bot:
        pw = int(W * 0.80)
        py = int(H * 0.05)
    else:
        pw = int(W * 0.88)
        py = (H - pw) // 2

    px = (W - pw) // 2
    return px, py, pw


# ── Image helpers ─────────────────────────────────────────────────────────────

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _darken(rgb, f=0.72):
    return tuple(max(0, int(c * f)) for c in rgb)


def _load_fonts():
    return (
        ImageFont.truetype(str(TOP_FONT), size=190),
        ImageFont.truetype(str(BOT_FONT), size=220),
    )


def _crop_photo(path, pw):
    img = Image.open(path).convert("RGB")
    aw, ah = img.size
    side   = min(aw, ah)
    img    = img.crop(((aw - side)//2, (ah - side)//2,
                       (aw + side)//2, (ah + side)//2))
    return img.resize((pw, pw), Image.LANCZOS)


def _draw_centered(draw, text, font, y, color, shadow):
    bbox = draw.textbbox((0, 0), text, font=font)
    x    = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x + 5, y + 5), text, font=font, fill=shadow)
    draw.text((x,     y    ), text, font=font, fill=color)


def _text_ys(draw, top_text, bottom_text, tf, bf, photo_y, photo_w):
    top_y = bot_y = None

    if top_text.strip():
        tb    = draw.textbbox((0, 0), top_text, font=tf)
        top_y = (photo_y - (tb[3] - tb[1])) // 2 - 10

    if bottom_text.strip():
        bb    = draw.textbbox((0, 0), bottom_text, font=bf)
        zone  = H - (photo_y + photo_w)
        bot_y = photo_y + photo_w + (zone - (bb[3] - bb[1])) // 2 - 10

    return top_y, bot_y


def _compose(mode, bg, photo, px, py, pw, top, bot, tf, bf, tc, sc):
    canvas = Image.new(mode, (W, H), color=bg)
    draw   = ImageDraw.Draw(canvas)
    canvas.paste(photo, (px, py))
    ty, by = _text_ys(draw, top, bot, tf, bf, py, pw)
    if ty is not None:
        _draw_centered(draw, top, tf, ty, tc, sc)
    if by is not None:
        _draw_centered(draw, bot, bf, by, tc, sc)
    return canvas


def _make_mockup(design_rgba, shirt_hex):
    shirt_rgb = _hex_to_rgb(shirt_hex)

    shadow = Image.new("RGBA", (MW, MH), (0, 0, 0, 0))
    sd     = ImageDraw.Draw(shadow)
    sd.polygon([(x+10, y+10) for x, y in SHIRT_PTS], fill=(0, 0, 0, 50))

    canvas = Image.new("RGBA", (MW, MH), MOCKUP_BG + (255,))
    canvas = Image.alpha_composite(canvas, shadow)
    draw   = ImageDraw.Draw(canvas)

    draw.polygon(SHIRT_PTS, fill=shirt_rgb + (255,))

    nx, ny, nrx, nry = NECK["cx"], NECK["cy"], NECK["rx"], NECK["ry"]
    draw.ellipse([nx-nrx, ny-nry, nx+nrx, ny+nry], fill=MOCKUP_BG + (255,))

    outline = _darken(shirt_rgb) if shirt_rgb != (255, 255, 255) else (185, 185, 185)
    draw.polygon(SHIRT_PTS, outline=outline + (255,))
    draw.line([SHIRT_PTS[1], SHIRT_PTS[4]],  fill=outline + (255,), width=1)
    draw.line([SHIRT_PTS[7], SHIRT_PTS[10]], fill=outline + (255,), width=1)

    dh  = int(CHEST_W * design_rgba.height / design_rgba.width)
    des = design_rgba.resize((CHEST_W, dh), Image.LANCZOS)
    canvas.paste(des, ((MW - CHEST_W) // 2, CHEST_Y), mask=des.split()[3])

    return canvas.convert("RGB")


# ── Upload / token helpers ────────────────────────────────────────────────────

def _slugify(text):
    slug = re.sub(r"\s+", "_", text.strip().lower())
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    return slug


# ── Security headers ──────────────────────────────────────────────────────────

@app.after_request
def _security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "img-src 'self' https://*.public.blob.vercel-storage.com; "
        # Presigned Blob PUT URLs are issued on vercel.com (confirmed against
        # this project's own deployment — not blob.vercel-storage.com, which
        # is only the plain read-write-token REST host storage.py talks to).
        "connect-src 'self' https://vercel.com "
        "https://blob.vercel-storage.com "
        "https://*.public.blob.vercel-storage.com;"
    )
    return resp


@app.context_processor
def _inject_app_version():
    return {"app_version": APP_VERSION}


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html", result=None,
        text_colours=TEXT_COLOURS, shirt_colours=SHIRT_COLOURS,
        form={},
    )


PHOTO_PATHNAME_RE = re.compile(r"^uploads/[0-9a-f-]+\.(jpg|png|webp)$")


@app.route("/generate", methods=["POST"])
@limiter.limit("10 per minute")
def generate():
    photo_pathname = (request.form.get("photo_pathname") or "").strip()
    top_text    = (request.form.get("top_text")     or "").strip()
    bottom_text = (request.form.get("bottom_text")  or "").strip()
    filename    = (request.form.get("filename")     or "").strip()
    text_colour  = request.form.get("text_colour", "White")
    shirt_colour = request.form.get("shirt_colour", next(iter(SHIRT_COLOURS)))

    sticky_form = {
        "top_text": top_text, "bottom_text": bottom_text,
        "filename": filename, "text_colour": text_colour,
        "shirt_colour": shirt_colour,
    }

    def _bounce(message):
        flash(message)
        return render_template(
            "index.html", result=None,
            text_colours=TEXT_COLOURS, shirt_colours=SHIRT_COLOURS,
            form=sticky_form,
        ), 400

    if not photo_pathname:
        return _bounce("Please upload a photograph.")

    if not PHOTO_PATHNAME_RE.match(photo_pathname):
        return _bounce("That upload looks invalid — please try uploading again.")

    photo_bytes = storage.get_blob_bytes(storage.blob_url(photo_pathname))
    if photo_bytes is None:
        return _bounce("That upload has expired — please upload the photo again.")

    if text_colour not in TEXT_COLOURS:
        text_colour = "White"
    if shirt_colour not in SHIRT_COLOURS:
        shirt_colour = next(iter(SHIRT_COLOURS))

    slug = _slugify(filename) or _slugify(bottom_text)
    if not slug:
        return _bounce(
            "Please enter a bottom text or fill in 'Save as' — "
            "needed to name the output files."
        )

    tc, sc    = TEXT_COLOURS[text_colour]["rgb"], TEXT_COLOURS[text_colour]["shadow"]
    shirt_hex = SHIRT_COLOURS[shirt_colour]

    tf, bf     = _load_fonts()
    px, py, pw = _get_layout(top_text, bottom_text)

    with tempfile.TemporaryDirectory() as tmp_dir:
        photo_path = Path(tmp_dir) / "upload"
        photo_path.write_bytes(photo_bytes)
        photo_img = _crop_photo(photo_path, pw)

        tiff_buf = io.BytesIO()
        _compose("RGB", (0, 0, 0), photo_img, px, py, pw,
                 top_text, bottom_text, tf, bf, tc, sc
                 ).save(tiff_buf, format="TIFF", compression="lzw")

        png = _compose("RGBA", (0, 0, 0, 0), photo_img, px, py, pw,
                       top_text, bottom_text, tf, bf,
                       tc + (255,), sc + (180,))
        png_buf = io.BytesIO()
        png.save(png_buf, format="PNG")

        mockup = _make_mockup(png, shirt_hex)
        mockup_buf = io.BytesIO()
        mockup.save(mockup_buf, format="JPEG", quality=93)

        preview = Image.new("RGB", (W, H), (80, 80, 80))
        preview.paste(png, mask=png.split()[3])
        preview_buf = io.BytesIO()
        preview.save(preview_buf, format="JPEG", quality=90)

    token  = uuid.uuid4().hex
    prefix = f"results/{token}"

    tiff_blob    = storage.put_blob(f"{prefix}/{slug}.tiff", tiff_buf.getvalue(), "image/tiff")
    png_blob     = storage.put_blob(f"{prefix}/{slug}.png", png_buf.getvalue(), "image/png")
    mockup_blob  = storage.put_blob(f"{prefix}/{slug}_mockup.jpg", mockup_buf.getvalue(), "image/jpeg")
    preview_blob = storage.put_blob(f"{prefix}/preview.jpg", preview_buf.getvalue(), "image/jpeg")

    meta = {
        "slug": slug,
        "preview_url": preview_blob["url"],
        "mockup_preview_url": mockup_blob["url"],
        "tiff_download_url": tiff_blob["downloadUrl"],
        "png_download_url": png_blob["downloadUrl"],
        "mockup_download_url": mockup_blob["downloadUrl"],
    }
    storage.put_blob(f"{prefix}/meta.json", json.dumps(meta).encode(), "application/json")

    return redirect(url_for("result", token=token))


@app.route("/result/<token>")
def result(token):
    if not TOKEN_RE.match(token):
        abort(404)

    meta_bytes = storage.get_blob_bytes(storage.blob_url(f"results/{token}/meta.json"))
    if meta_bytes is None:
        flash("That result has expired — please generate again.")
        return redirect(url_for("index"))

    meta = json.loads(meta_bytes)
    return render_template(
        "index.html",
        result=meta, token=token,
        text_colours=TEXT_COLOURS, shirt_colours=SHIRT_COLOURS,
        form={},
    )


@app.route("/download/<token>")
def download(token):
    if not TOKEN_RE.match(token):
        abort(404)

    meta_bytes = storage.get_blob_bytes(storage.blob_url(f"results/{token}/meta.json"))
    if meta_bytes is None:
        flash("That result has expired — please generate again.")
        return redirect(url_for("index"))

    meta = json.loads(meta_bytes)
    slug = meta["slug"]
    files = [
        (f"{slug}.tiff",        meta["tiff_download_url"]),
        (f"{slug}.png",         meta["png_download_url"]),
        (f"{slug}_mockup.jpg",  meta["mockup_download_url"]),
    ]

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, url in files:
            data = storage.get_blob_bytes(url)
            if data is None:
                abort(404)
            zf.writestr(arcname, data)

    return Response(
        zip_buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}_design.zip"'},
    )


@app.route("/_health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
