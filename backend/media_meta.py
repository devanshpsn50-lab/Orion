"""
Orion — media_meta.py
Extracts rich metadata from image, audio, and video files.
"""

import os
import struct
from pathlib import Path

# ── Image EXIF (via Pillow) ───────────────────────────────────────────────────
def get_image_meta(path: str) -> dict:
    """Extract image metadata: dimensions, EXIF data, camera, date taken."""
    meta = {}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        with Image.open(path) as img:
            meta["width"]  = img.width
            meta["height"] = img.height
            meta["mode"]   = img.mode
            meta["format"] = img.format

            # Determine resolution tier
            px = img.width * img.height
            if px >= 3840 * 2160:
                meta["resolution_label"] = "4k"
            elif px >= 1920 * 1080:
                meta["resolution_label"] = "1080p"
            elif px >= 1280 * 720:
                meta["resolution_label"] = "720p"
            else:
                meta["resolution_label"] = "sd"

            # EXIF data
            exif_data = img._getexif() if hasattr(img, "_getexif") else None
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, str(tag_id))
                    if tag == "DateTimeOriginal":
                        meta["date_taken"] = str(value)
                    elif tag == "Make":
                        meta["camera_make"] = str(value).strip()
                    elif tag == "Model":
                        meta["camera_model"] = str(value).strip()
                    elif tag == "GPSInfo":
                        meta["has_gps"] = True
                    elif tag == "FocalLength":
                        meta["focal_length"] = str(value)
                    elif tag == "ISOSpeedRatings":
                        meta["iso"] = int(value) if isinstance(value, (int, float)) else str(value)

    except Exception:
        pass
    return meta


def get_thumbnail_b64(path: str, size: tuple = (400, 300)) -> str | None:
    """Return a base64-encoded JPEG thumbnail of an image file."""
    try:
        import io, base64
        from PIL import Image, ImageOps

        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)   # correct orientation
            img.thumbnail(size, Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


# ── Audio Metadata (via mutagen) ──────────────────────────────────────────────
def get_audio_meta(path: str) -> dict:
    """Extract audio metadata: artist, album, title, duration, bitrate."""
    meta = {}
    try:
        import mutagen
        from mutagen.mp3  import MP3
        from mutagen.flac import FLAC
        from mutagen.mp4  import MP4
        from mutagen.id3  import ID3NoHeaderError

        ext = Path(path).suffix.lower()

        audio = mutagen.File(path, easy=True)
        if audio is None:
            return meta

        # Duration
        if hasattr(audio, "info") and hasattr(audio.info, "length"):
            meta["duration"] = int(audio.info.length)

        # Bitrate
        if hasattr(audio, "info") and hasattr(audio.info, "bitrate"):
            meta["bitrate"] = audio.info.bitrate

        # Tags (easy tag interface)
        for tag, key in [("title", "title"), ("artist", "artist"),
                         ("album", "album"),  ("date", "year"),
                         ("genre", "genre"),  ("tracknumber", "track")]:
            val = audio.get(tag)
            if val:
                meta[key] = str(val[0]) if isinstance(val, list) else str(val)

        # Album art availability
        if ext in (".mp3", ".flac", ".m4a", ".ogg"):
            audio_raw = mutagen.File(path)
            if audio_raw:
                if hasattr(audio_raw, "pictures") and audio_raw.pictures:
                    meta["has_album_art"] = True
                elif any(k.startswith("APIC") for k in audio_raw.keys()):
                    meta["has_album_art"] = True

    except Exception:
        pass
    return meta


def get_audio_albumart_b64(path: str) -> str | None:
    """Return base64-encoded album art from an audio file."""
    try:
        import base64
        import mutagen
        from mutagen.id3 import ID3

        audio = mutagen.File(path)
        if audio is None:
            return None

        # FLAC
        if hasattr(audio, "pictures") and audio.pictures:
            return base64.b64encode(audio.pictures[0].data).decode()

        # MP3 (ID3 APIC frames)
        for key in audio.keys():
            if key.startswith("APIC"):
                return base64.b64encode(audio[key].data).decode()

        # M4A cover
        if "covr" in audio:
            covers = audio["covr"]
            if covers:
                return base64.b64encode(bytes(covers[0])).decode()

    except Exception:
        pass
    return None


# ── Video Metadata ────────────────────────────────────────────────────────────
def get_video_meta(path: str) -> dict:
    """Extract video metadata using mutagen and basic container parsing."""
    meta = {}
    try:
        import mutagen
        f = mutagen.File(path)
        if f and hasattr(f, "info"):
            info = f.info
            if hasattr(info, "length"):
                meta["duration"] = int(info.length)
            if hasattr(info, "bitrate"):
                meta["bitrate"] = info.bitrate

        # Try to get resolution from MP4 container
        ext = Path(path).suffix.lower()
        if ext in (".mp4", ".m4v", ".mov"):
            w, h = _mp4_dimensions(path)
            if w and h:
                meta["width"]  = w
                meta["height"] = h
                px = w * h
                if px >= 3840 * 2160:
                    meta["resolution_label"] = "4k"
                elif px >= 1920 * 1080:
                    meta["resolution_label"] = "1080p"
                elif px >= 1280 * 720:
                    meta["resolution_label"] = "720p"
                else:
                    meta["resolution_label"] = "sd"

    except Exception:
        pass
    return meta


def _mp4_dimensions(path: str) -> tuple[int, int]:
    """Quick-parse MP4/MOV to extract video track dimensions."""
    try:
        with open(path, "rb") as f:
            data = f.read(min(1024 * 1024, os.path.getsize(path)))   # first 1 MB
        idx = data.find(b"tkhd")
        if idx == -1:
            return 0, 0
        # tkhd box: 4 bytes size, 4 bytes type, then version/flags + fields
        # width and height are near the end of tkhd
        tkhd = data[idx:]
        if len(tkhd) < 92:
            return 0, 0
        # Version 0 tkhd: 4+4+4+4+4+4+4+4+8+2+2+2+2+36+4+4 = 92 bytes total
        w = struct.unpack(">I", tkhd[76:80])[0] >> 16
        h = struct.unpack(">I", tkhd[80:84])[0] >> 16
        return w, h
    except Exception:
        return 0, 0


def format_duration(seconds: int) -> str:
    """Format seconds into HH:MM:SS or MM:SS string."""
    if seconds is None:
        return ""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_size(bytes_: int) -> str:
    """Human-readable file size."""
    if bytes_ is None or bytes_ == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}" if unit != "B" else f"{bytes_} B"
        bytes_ /= 1024
    return f"{bytes_:.1f} PB"
