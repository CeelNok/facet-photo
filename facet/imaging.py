"""Image decoding tuned for low CPU and memory use.

* JPEGs are decoded with libjpeg DCT scaling (Pillow ``draft``), so a 24 MP photo is decoded
  at 1/8 size for a thumbnail instead of being fully decoded and then shrunk.
* RAW files use the JPEG preview the camera embedded in the file; the sensor data is only
  demosaiced (LibRaw) when no usable preview exists or a full-quality render is requested.
"""

from __future__ import annotations

import io
import math
import os

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 400_000_000

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover - optional
    HEIF_OK = False

try:
    import rawpy

    RAW_OK = True
except Exception:  # pragma: no cover - optional
    rawpy = None
    RAW_OK = False

RAW_EXTS = {
    ".3fr", ".ari", ".arw", ".bay", ".cr2", ".cr3", ".crw", ".dcr", ".dng", ".erf", ".fff", ".iiq",
    ".k25", ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2",
    ".rwl", ".sr2", ".srf", ".srw", ".x3f",
}
IMAGE_EXTS = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".webp", ".bmp", ".gif"}
if HEIF_OK:
    IMAGE_EXTS |= {".heic", ".heif", ".hif"}
SUPPORTED_EXTS = IMAGE_EXTS | (RAW_EXTS if RAW_OK else set())

# TypeSafe image limits (https://docs.typesafe.ai/images#limits)
AI_MAX_SIDE = 1568
AI_MIN_SIDE = 280  # 280 x 280 also satisfies the 78,400 px minimum area


def is_raw(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in RAW_EXTS


def _draft(im: Image.Image, long_side: int) -> None:
    """Ask the JPEG decoder to decode at the smallest DCT scale that still covers long_side."""
    if im.format != "JPEG":
        return
    w, h = im.size
    s = long_side / max(w, h)
    if s < 1:
        im.draft("RGB", (max(1, math.ceil(w * s)), max(1, math.ceil(h * s))))


_FLIP_TO_TRANSPOSE = {
    3: Image.Transpose.ROTATE_180,
    5: Image.Transpose.ROTATE_90,   # LibRaw: 90° counter-clockwise
    6: Image.Transpose.ROTATE_270,  # LibRaw: 90° clockwise
}


def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode == "RGB":
        return im
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    if im.mode.startswith("I;16") or im.mode == "I":
        im = im.point(lambda v: v * (1 / 256)).convert("L")
    return im.convert("RGB")


def _load_raw(path: str, long_side: int | None, full: bool) -> Image.Image:
    with rawpy.imread(path) as raw:
        flip = raw.sizes.flip
        im = None
        if not full:
            try:
                th = raw.extract_thumb()
                if th.format == rawpy.ThumbFormat.JPEG:
                    im = Image.open(io.BytesIO(th.data))
                    if long_side:
                        _draft(im, long_side)
                    im.load()
                    orientation = im.getexif().get(0x0112, 1)
                    if orientation != 1:
                        ImageOps.exif_transpose(im, in_place=True)
                        flip = 0
                elif th.format == rawpy.ThumbFormat.BITMAP:
                    im = Image.fromarray(th.data)
            except Exception:
                im = None
            # Develop the RAW instead when the embedded preview is too small for the request:
            # below ~1200 px for screen use, or clearly below sensor size for full-resolution zoom.
            if im is not None:
                sensor = max(raw.sizes.width, raw.sizes.height)
                if long_side:
                    too_small = max(im.size) < min(long_side, 1200)
                else:
                    too_small = max(im.size) < 0.9 * sensor
                if too_small:
                    im = None
        if im is None:
            half = bool(long_side) and long_side <= max(raw.sizes.width, raw.sizes.height) // 2
            rgb = raw.postprocess(half_size=half, use_camera_wb=True, output_bps=8)
            im = Image.fromarray(rgb)
            del rgb
            flip = 0  # postprocess already rotates
    if flip in _FLIP_TO_TRANSPOSE:
        im = im.transpose(_FLIP_TO_TRANSPOSE[flip])
    return im


def load_image(path: str, long_side: int | None = None, raw_full: bool = False) -> Image.Image:
    """Decode an upright RGB image whose longest side is at most ``long_side`` (None = full size)."""
    if is_raw(path):
        if not RAW_OK:
            raise RuntimeError("RAW support (rawpy) is not installed")
        im = _load_raw(path, long_side, raw_full)
    else:
        im = Image.open(path)
        if getattr(im, "is_animated", False):
            im.seek(0)
        if long_side:
            _draft(im, long_side)
        im.load()
        ImageOps.exif_transpose(im, in_place=True)
    im = _to_rgb(im)
    if long_side and max(im.size) > long_side:
        im.thumbnail((long_side, long_side), Image.Resampling.BICUBIC, reducing_gap=2.0)
    return im


def make_thumbnail_jpeg(path: str, long_side: int, dest: str) -> Image.Image:
    im = load_image(path, long_side)
    tmp = dest + ".tmp"
    im.save(tmp, "JPEG", quality=82)
    os.replace(tmp, dest)
    return im


def prepare_for_ai(path: str, max_side: int = 1024) -> bytes:
    """Return a baseline JPEG within TypeSafe's size limits (upright, metadata stripped)."""
    max_side = max(AI_MIN_SIDE, min(AI_MAX_SIDE, max_side))
    im = load_image(path, max_side)
    w, h = im.size
    if min(w, h) < AI_MIN_SIDE:
        scale = AI_MIN_SIDE / min(w, h)
        if max(w, h) * scale <= AI_MAX_SIDE:
            im = im.resize((math.ceil(w * scale), math.ceil(h * scale)), Image.Resampling.BICUBIC)
        else:  # extreme panorama: fit the long side, then pad the short side
            scale = AI_MAX_SIDE / max(w, h)
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.BICUBIC)
            canvas = Image.new("RGB", (max(im.width, AI_MIN_SIDE), max(im.height, AI_MIN_SIDE)), (0, 0, 0))
            canvas.paste(im, ((canvas.width - im.width) // 2, (canvas.height - im.height) // 2))
            im = canvas
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85, progressive=False)
    return buf.getvalue()


def crop_face(path: str, rect: tuple[float, float, float, float], margin: float = 0.35) -> bytes:
    """Cut a reference face out of a photo.

    ``rect`` is (x0, y0, x1, y1) as fractions of the upright image. A margin around the face keeps
    hair and outline, which helps recognition. The crop is sized to TypeSafe's limits.
    """
    im = load_image(path, 2400)
    w, h = im.size
    x0, y0, x1, y1 = rect
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    mw, mh = (x1 - x0) * margin, (y1 - y0) * margin
    box = (
        max(0, int((x0 - mw) * w)), max(0, int((y0 - mh) * h)),
        min(w, int(math.ceil((x1 + mw) * w))), min(h, int(math.ceil((y1 + mh) * h))),
    )
    if box[2] - box[0] < 4 or box[3] - box[1] < 4:
        raise ValueError("selection too small")
    face = im.crop(box)
    cw, ch = face.size
    scale = 1.0
    if min(cw, ch) < AI_MIN_SIDE:
        scale = AI_MIN_SIDE / min(cw, ch)
    elif max(cw, ch) > 640:
        scale = 640 / max(cw, ch)
    if scale != 1.0:
        face = face.resize((max(AI_MIN_SIDE, round(cw * scale)), max(AI_MIN_SIDE, round(ch * scale))),
                           Image.Resampling.BICUBIC)
    if max(face.size) > AI_MAX_SIDE:
        face.thumbnail((AI_MAX_SIDE, AI_MAX_SIDE))
    buf = io.BytesIO()
    face.save(buf, "JPEG", quality=90)
    return buf.getvalue()
