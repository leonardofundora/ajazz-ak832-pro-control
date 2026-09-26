"""Converts images/GIFs to the screen format (160x96, little-endian RGB565)."""

from PIL import Image, ImageOps, ImageSequence

from . import protocol as P

SIZE = (P.SCREEN_W, P.SCREEN_H)


def fit_frame(img: Image.Image, mode: str = "fill", background=(0, 0, 0)) -> Image.Image:
    """mode: 'fill' crops to fill, 'fit' letterboxes, 'stretch' distorts."""
    img = img.convert("RGBA")
    if mode == "stretch":
        out = img.resize(SIZE, Image.LANCZOS)
    elif mode == "fit":
        out = ImageOps.contain(img, SIZE, Image.LANCZOS)
    else:
        out = ImageOps.fit(img, SIZE, Image.LANCZOS)
    canvas = Image.new("RGBA", SIZE, background + (255,))
    canvas.paste(out, ((SIZE[0] - out.width) // 2, (SIZE[1] - out.height) // 2), out)
    return canvas.convert("RGB")


def load_frames(path: str, mode: str = "fill"):
    """Returns (list of 160x96 RGB images, list of delays in ms)."""
    src = Image.open(path)
    frames, delays = [], []
    for f in ImageSequence.Iterator(src):
        frames.append(fit_frame(f.copy(), mode))
        d = f.info.get("duration", src.info.get("duration", 100)) or 100
        delays.append(max(P.MIN_DELAY_MS, min(P.MAX_DELAY_MS, int(d))))
        if len(frames) >= P.MAX_FRAMES:
            break
    return frames, delays


def to_rgb565(img: Image.Image) -> bytes:
    """Same as mui.dll GetImageRGB565Data: (R&F8)<<8 | (G&FC)<<3 | B>>3, low byte first."""
    img = img.convert("RGB")
    if img.size != SIZE:
        img = img.resize(SIZE)
    raw = img.tobytes()
    out = bytearray(len(raw) // 3 * 2)
    j = 0
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[j] = v & 0xFF
        out[j + 1] = v >> 8
        j += 2
    return bytes(out)
