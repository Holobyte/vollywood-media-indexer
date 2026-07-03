from __future__ import annotations

from pathlib import Path

APP_NAME = "Vollywood Media Indexer"
APP_VERSION = "0.3.0"
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / ".vmi_data"
DB_PATH = DATA_DIR / "media_index.db"
THUMBNAIL_DIR = DATA_DIR / "thumbnails"
CONTACT_SHEET_DIR = DATA_DIR / "contact_sheets"
EXPORT_DIR = DATA_DIR / "exports"

for path in (DATA_DIR, THUMBNAIL_DIR, CONTACT_SHEET_DIR, EXPORT_DIR):
    path.mkdir(parents=True, exist_ok=True)
