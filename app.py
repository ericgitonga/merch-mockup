"""
Flask app for the Insect Design Generator.

Upload a photo, add optional top/bottom text labels, pick a text colour and
a t-shirt colour, and get back a print-ready TIFF (black background), a
transparent PNG, and a t-shirt mockup JPG.

Ported from a Gradio prototype after Gradio proved unreliable to deploy on
Render — the image-processing pipeline below (crop/compose/mockup) is
unchanged from that prototype.
"""

import json
import os
import re
import secrets
import shutil
import time
import uuid
import warnings
from pathlib import Path

from flask import (
    Flask, abort, flash, redirect, render_template,
    request, send_file, url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"
TOP_FONT = ASSETS_DIR / "DancingScript-Bold.ttf"
BOT_FONT = ASSETS_DIR / "Kalam-Bold.ttf"

TEMP_ROOT = Path(os.environ.get("MERCH_MOCKUP_TMP", "/tmp/merch-mockup"))
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
TOKEN_MAX_AGE = 60 * 60  # 1 hour — bounds disk growth without a cron job
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

app = Flask(__name__)
APP_VERSION = (BASE_DIR / "VERSION").read_text().strip()

# ── Secret key ─────────────────────────────────────────────────────────────
# On Render, SECRET_KEY is set as an environment variable via the dashboard.
# Locally, if absent, auto-generate one so development is frictionless — the
# trade-off is CSRF tokens invalidate on every restart, which is fine in dev.
_secret = os.environ.get("SECRET_KEY", "")
if not _secret:
    _secret = secrets.token_hex(32)
    warnings.warn(
        "SECRET_KEY not set — using a randomly generated key. "
        "CSRF tokens will be invalidated on restart. "
        "Set SECRET_KEY in your environment (or Render dashboard) for production.",
        stacklevel=1,
    )
app.config["SECRET_KEY"] = _secret
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15 MB

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

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

def _safe_suffix(filename):
    """Return the lowercased extension of filename if it's on the allow-list.

    Raises ValueError otherwise — never trust the client's Content-Type.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{suffix or '(none)'}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return suffix


def _slugify(text):
    slug = re.sub(r"\s+", "_", text.strip().lower())
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    return slug


def _sweep_temp_root():
    """Best-effort removal of result directories older than TOKEN_MAX_AGE."""
    now = time.time()
    for entry in TEMP_ROOT.iterdir():
        try:
            if entry.is_dir() and (now - entry.stat().st_mtime) > TOKEN_MAX_AGE:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            continue


def _token_dir(token):
    """Validate token shape and existence, or abort(404). Never trust input."""
    if not TOKEN_RE.match(token):
        abort(404)
    out_dir = TEMP_ROOT / token
    if not out_dir.is_dir():
        abort(404)
    return out_dir


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
        "img-src 'self';"
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


@app.route("/generate", methods=["POST"])
@limiter.limit("10 per minute")
def generate():
    photo = request.files.get("photo")
    top_text    = (request.form.get("top_text")    or "").strip()
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

    if not photo or not photo.filename:
        return _bounce("Please upload a photograph.")

    try:
        upload_suffix = _safe_suffix(photo.filename)
    except ValueError as exc:
        return _bounce(str(exc))

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

    _sweep_temp_root()
    token = uuid.uuid4().hex
    out_dir = TEMP_ROOT / token
    out_dir.mkdir(parents=True)

    upload_path = out_dir / f"upload{upload_suffix}"
    photo.save(upload_path)

    tc, sc    = TEXT_COLOURS[text_colour]["rgb"], TEXT_COLOURS[text_colour]["shadow"]
    shirt_hex = SHIRT_COLOURS[shirt_colour]

    tf, bf     = _load_fonts()
    px, py, pw = _get_layout(top_text, bottom_text)
    photo_img  = _crop_photo(upload_path, pw)

    _compose("RGB", (0, 0, 0), photo_img, px, py, pw,
             top_text, bottom_text, tf, bf, tc, sc
             ).save(out_dir / f"{slug}.tiff", format="TIFF", compression="lzw")

    png = _compose("RGBA", (0, 0, 0, 0), photo_img, px, py, pw,
                   top_text, bottom_text, tf, bf,
                   tc + (255,), sc + (180,))
    png.save(out_dir / f"{slug}.png", format="PNG")

    mockup = _make_mockup(png, shirt_hex)
    mockup.save(out_dir / "mockup.jpg", format="JPEG", quality=93)

    preview = Image.new("RGB", (W, H), (80, 80, 80))
    preview.paste(png, mask=png.split()[3])
    preview.save(out_dir / "preview.jpg", format="JPEG", quality=90)

    upload_path.unlink(missing_ok=True)
    (out_dir / "meta.json").write_text(json.dumps({"slug": slug}))

    return redirect(url_for("result", token=token))


@app.route("/result/<token>")
def result(token):
    if not TOKEN_RE.match(token):
        abort(404)
    out_dir = TEMP_ROOT / token
    meta_path = out_dir / "meta.json"
    if not meta_path.is_file():
        flash("That result has expired — please generate again.")
        return redirect(url_for("index"))
    slug = json.loads(meta_path.read_text())["slug"]
    return render_template(
        "index.html",
        result={"token": token, "slug": slug},
        text_colours=TEXT_COLOURS, shirt_colours=SHIRT_COLOURS,
        form={},
    )


@app.route("/preview/<token>/<kind>")
def preview_image(token, kind):
    if kind not in ("design", "mockup"):
        abort(404)
    out_dir = _token_dir(token)
    path = out_dir / ("preview.jpg" if kind == "design" else "mockup.jpg")
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="image/jpeg")


@app.route("/download/<token>/<kind>")
def download(token, kind):
    out_dir = _token_dir(token)
    meta_path = out_dir / "meta.json"
    if not meta_path.is_file():
        abort(404)
    slug = json.loads(meta_path.read_text())["slug"]

    files = {
        "tiff":   (out_dir / f"{slug}.tiff", f"{slug}.tiff",        "image/tiff"),
        "png":    (out_dir / f"{slug}.png",  f"{slug}.png",         "image/png"),
        "mockup": (out_dir / "mockup.jpg",   f"{slug}_mockup.jpg",  "image/jpeg"),
    }
    if kind not in files:
        abort(404)
    path, download_name, mimetype = files[kind]
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True,
                     download_name=download_name, mimetype=mimetype)


@app.route("/_health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
