import base64
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.models.chart import Chart

def chart_id_for_folder(folder: str) -> str:
    """Encode folder relative path to URL-safe Base64 without padding (exact Go parity)."""
    clean_folder = folder.replace("\\", "/").strip("/")
    encoded = base64.urlsafe_b64encode(clean_folder.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")

def folder_for_chart_id(chart_id: str) -> str:
    """Decode Base64 chart ID to folder path with path-traversal safety check."""
    padded = chart_id + "=" * ((4 - len(chart_id) % 4) % 4)
    folder_bytes = base64.urlsafe_b64decode(padded)
    folder_str = folder_bytes.decode("utf-8").replace("\\", "/")
    
    # Path traversal check
    clean_path = Path(folder_str)
    if clean_path.is_absolute() or ".." in clean_path.parts:
        raise ValueError("Invalid chart ID path")
    return folder_str

def parse_maidata(data: bytes) -> dict:
    """
    Parse maidata.txt metadata (title, artist, designer, lv_1 to lv_7).
    Exact parity with MajdataProvider parser.go.
    """
    text = data.decode("utf-8-sig", errors="replace")
    title = ""
    artist = ""
    designer = ""
    levels: List[Optional[str]] = [None] * 7

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("&title="):
            title = line[len("&title="):]
        elif line.startswith("&artist="):
            artist = line[len("&artist="):]
        elif line.startswith("&des="):
            designer = line[len("&des="):]
        elif line.startswith("&lv_"):
            if "=" in line:
                key, val = line.split("=", 1)
                lvl_str = key[len("&lv_"):]
                val = val.strip()
                if lvl_str.isdigit() and val:
                    idx = int(lvl_str)
                    if 1 <= idx <= 7:
                        levels[idx - 1] = val

    return {
        "title": title,
        "artist": artist,
        "designer": designer,
        "levels": levels,
    }

def compute_maidata_hash(data: bytes) -> str:
    """Calculate base64 encoded MD5 of maidata.txt (used for scores and game integrity check)."""
    return base64.b64encode(hashlib.md5(data).digest()).decode("ascii")

def compute_sha256_hash(data: bytes) -> str:
    """Calculate base64 encoded SHA256 of file (used for HTTP response 'hash' header)."""
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")

async def scan_and_sync_charts(db: AsyncSession) -> int:
    """Scan CHARTS_DIR, parse all maidata.txt files, and synchronize with the database."""
    charts_dir = settings.CHARTS_DIR
    if not charts_dir.exists():
        return 0

    count = 0
    # Walk all folders looking for maidata.txt
    for maidata_path in charts_dir.rglob("maidata.txt"):
        folder_path = maidata_path.parent
        rel_folder = folder_path.relative_to(charts_dir).as_posix()
        if rel_folder == ".":
            continue

        try:
            data = maidata_path.read_bytes()
            stat = maidata_path.stat()
            mod_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            
            parsed = parse_maidata(data)
            chart_id = chart_id_for_folder(rel_folder)
            chart_hash = compute_maidata_hash(data)

            # Check if chart exists in DB
            stmt = select(Chart).where(Chart.id == chart_id)
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.folder_path = rel_folder
                existing.title = parsed["title"]
                existing.artist = parsed["artist"]
                existing.designer = parsed["designer"]
                existing.levels_json = parsed["levels"]
                existing.hash = chart_hash
                existing.timestamp = mod_time
            else:
                new_chart = Chart(
                    id=chart_id,
                    folder_path=rel_folder,
                    title=parsed["title"],
                    artist=parsed["artist"],
                    designer=parsed["designer"],
                    uploader="System",
                    description="",
                    hash=chart_hash,
                    levels_json=parsed["levels"],
                    tags_json=[],
                    public_tags_json=[],
                    timestamp=mod_time,
                )
                db.add(new_chart)
            count += 1
        except Exception as e:
            print(f"Error processing chart at {maidata_path}: {e}")

    await db.commit()
    return count
