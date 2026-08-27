import mimetypes
from pathlib import Path
from typing import Optional, List
from fastapi import Response, HTTPException
from fastapi.responses import Response
from app.config import settings
from app.services.chart_scanner import compute_sha256_hash, folder_for_chart_id
from app.services.image_service import get_thumbnail_bytes

WEEK_CACHE_CONTROL = "public,max-age=604800"

def get_chart_folder_path(chart_id: str) -> Path:
    """Get absolute folder path for a given chart_id, ensuring safe resolution."""
    try:
        folder_rel = folder_for_chart_id(chart_id)
        folder_path = (settings.CHARTS_DIR / folder_rel).resolve()
        
        # Verify it is inside settings.CHARTS_DIR
        if not folder_path.is_relative_to(settings.CHARTS_DIR.resolve()):
            raise HTTPException(status_code=404, detail="Chart not found")
        if not folder_path.exists() or not folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Chart folder not found")
        return folder_path
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid chart ID")

def find_first_existing_file(dir_path: Path, candidates: List[str]) -> Optional[Path]:
    """Find the first matching file from candidate names."""
    for name in candidates:
        candidate_path = dir_path / name
        if candidate_path.exists() and candidate_path.is_file():
            return candidate_path
    return None

def create_hashed_file_response(
    data: bytes,
    content_type: str,
    download_filename: Optional[str] = None
) -> Response:
    """Build response containing SHA-256 hash header and cache headers matching Go provider."""
    sha256_hash = compute_sha256_hash(data)
    headers = {
        "hash": sha256_hash,
        "Content-Length": str(len(data)),
        "Cache-Control": WEEK_CACHE_CONTROL,
        "Accept-Ranges": "bytes",
    }
    if download_filename:
        headers["Content-Disposition"] = f'attachment; filename="{download_filename}"'
        
    return Response(
        content=data,
        media_type=content_type,
        headers=headers
    )
