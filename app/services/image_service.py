import os
import io
from pathlib import Path
from typing import Tuple
from PIL import Image
from app.config import settings

MAX_THUMBNAIL_PIXEL = 512

def get_thumbnail_bytes(image_path: Path) -> Tuple[bytes, str]:
    """
    Generate resized thumbnail image (max 512px) in JPEG or PNG format.
    Maintains aspect ratio with Lanczos scaling.
    """
    with Image.open(image_path) as img:
        img_format = img.format or "JPEG"
        
        # Calculate new dimensions
        width, height = img.size
        if width > MAX_THUMBNAIL_PIXEL or height > MAX_THUMBNAIL_PIXEL:
            img.thumbnail((MAX_THUMBNAIL_PIXEL, MAX_THUMBNAIL_PIXEL), Image.Resampling.LANCZOS)
        
        out_io = io.BytesIO()
        if img_format.upper() == "PNG":
            img.save(out_io, format="PNG")
            return out_io.getvalue(), "image/png"
        else:
            # Convert RGBA to RGB for JPEG if necessary
            if img.mode in ("RGBA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
                rgb_img.save(out_io, format="JPEG", quality=85)
            else:
                img.save(out_io, format="JPEG", quality=85)
            return out_io.getvalue(), "image/jpeg"
