"""Extract only a bounded standard JPEG stream; no proprietary format decoding."""
from .engine import safe

def jpeg_bytes(path):
    p = safe(path)
    if p.stat().st_size > 2 * 1024 * 1024:
        return None
    data = p.read_bytes()
    start = data.find(b'\xff\xd8\xff')
    end = data.find(b'\xff\xd9', start + 3) if start >= 0 else -1
    return data[start:end + 2] if 0 <= start < end else None
