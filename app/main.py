from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME, APP_VERSION, DB_PATH, EXPORT_DIR, SUPPORTED_VIDEO_EXTENSIONS, THUMBNAIL_DIR

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                current_filename TEXT NOT NULL,
                full_path TEXT NOT NULL UNIQUE,
                folder_path TEXT NOT NULL,
                file_ext TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                created_at TEXT,
                modified_at TEXT,
                duration_seconds REAL,
                width INTEGER,
                height INTEGER,
                codec TEXT,
                frame_rate TEXT,
                thumbnail_path TEXT,
                fingerprint TEXT,
                project_name TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                suggested_filename TEXT DEFAULT '',
                approval_status TEXT DEFAULT 'needs-review',
                rating INTEGER DEFAULT 0,
                missing INTEGER DEFAULT 0,
                indexed_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rename_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id INTEGER,
                old_path TEXT NOT NULL,
                new_path TEXT NOT NULL,
                old_filename TEXT NOT NULL,
                new_filename TEXT NOT NULL,
                renamed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS note_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id INTEGER,
                preset_key TEXT NOT NULL,
                content TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL,
                recursive INTEGER DEFAULT 1,
                files_seen INTEGER DEFAULT 0,
                files_added INTEGER DEFAULT 0,
                files_updated INTEGER DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                message TEXT DEFAULT ''
            )
            """
        )
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()


def ffprobe(path: Path) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        return {}
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,r_frame_rate:format=duration",
        "-of", "json", str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        duration = fmt.get("duration")
        return {
            "duration_seconds": round(float(duration), 2) if duration else None,
            "width": stream.get("width"),
            "height": stream.get("height"),
            "codec": stream.get("codec_name"),
            "frame_rate": stream.get("r_frame_rate"),
        }
    except Exception:
        return {}


def make_thumb(path: Path) -> str | None:
    if shutil.which("ffmpeg") is None:
        return None
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    out = THUMBNAIL_DIR / f"{abs(hash(str(path)))}.jpg"
    cmd = ["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(path), "-frames:v", "1", "-q:v", "3", str(out)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        return str(out) if result.returncode == 0 and out.exists() else None
    except Exception:
        return None


def fingerprint(meta: dict[str, Any], p: Path) -> str:
    parts = [str(p.stat().st_size), str(meta.get("duration_seconds") or ""), str(meta.get("width") or ""), str(meta.get("height") or ""), str(meta.get("codec") or ""), p.suffix.lower()]
    return "|".join(parts)


def iter_videos(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return [p for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS]


def scan_folder(folder_path: str, recursive: bool = True, thumbnails: bool = True) -> dict[str, Any]:
    folder = Path(folder_path).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError("Folder does not exist or is not a directory")
    start = now()
    added = updated = 0
    files = iter_videos(folder, recursive)
    with db() as conn:
        for path in files:
            stat = path.stat()
            meta = ffprobe(path)
            thumb = make_thumb(path) if thumbnails else None
            fp = fingerprint(meta, path)
            existing = conn.execute("SELECT id, thumbnail_path FROM media_files WHERE full_path=?", (str(path),)).fetchone()
            payload = {
                "original_filename": path.name,
                "current_filename": path.name,
                "full_path": str(path),
                "folder_path": str(path.parent),
                "file_ext": path.suffix.lower(),
                "file_size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(timespec="seconds"),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "duration_seconds": meta.get("duration_seconds"),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "codec": meta.get("codec"),
                "frame_rate": meta.get("frame_rate"),
                "thumbnail_path": thumb or (existing["thumbnail_path"] if existing else None),
                "fingerprint": fp,
                "indexed_at": now(),
                "last_seen_at": now(),
            }
            if existing:
                updated += 1
                conn.execute(
                    """
                    UPDATE media_files SET current_filename=:current_filename, folder_path=:folder_path,
                    file_size=:file_size, modified_at=:modified_at, duration_seconds=:duration_seconds,
                    width=:width, height=:height, codec=:codec, frame_rate=:frame_rate,
                    thumbnail_path=:thumbnail_path, fingerprint=:fingerprint, last_seen_at=:last_seen_at,
                    missing=0 WHERE id=:id
                    """,
                    {**payload, "id": existing["id"]},
                )
            else:
                added += 1
                conn.execute(
                    """
                    INSERT INTO media_files (original_filename,current_filename,full_path,folder_path,file_ext,file_size,created_at,modified_at,duration_seconds,width,height,codec,frame_rate,thumbnail_path,fingerprint,indexed_at,last_seen_at)
                    VALUES (:original_filename,:current_filename,:full_path,:folder_path,:file_ext,:file_size,:created_at,:modified_at,:duration_seconds,:width,:height,:codec,:frame_rate,:thumbnail_path,:fingerprint,:indexed_at,:last_seen_at)
                    """,
                    payload,
                )
        conn.execute(
            "INSERT INTO scan_events (folder_path, recursive, files_seen, files_added, files_updated, started_at, finished_at, message) VALUES (?,?,?,?,?,?,?,?)",
            (str(folder), int(recursive), len(files), added, updated, start, now(), "Scan complete"),
        )
        conn.commit()
    return {"seen": len(files), "added": added, "updated": updated}


def list_media(q: str = "", status: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM media_files WHERE 1=1"
    params: list[Any] = []
    if q:
        like = f"%{q}%"
        sql += " AND (current_filename LIKE ? OR folder_path LIKE ? OR tags LIKE ? OR notes LIKE ? OR project_name LIKE ? OR codec LIKE ?)"
        params += [like] * 6
    if status:
        sql += " AND approval_status=?"
        params.append(status)
    sql += " ORDER BY modified_at DESC LIMIT 500"
    with db() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_media(media_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM media_files WHERE id=?", (media_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Media not found")
        return dict(row)


def stats() -> dict[str, Any]:
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM media_files").fetchone()["c"]
        size = conn.execute("SELECT COALESCE(SUM(file_size),0) s FROM media_files").fetchone()["s"]
        needs = conn.execute("SELECT COUNT(*) c FROM media_files WHERE approval_status='needs-review'").fetchone()["c"]
        latest = conn.execute("SELECT * FROM scan_events ORDER BY id DESC LIMIT 1").fetchone()
    return {"total": total, "total_size_gb": round(size / 1_000_000_000, 2), "needs_review": needs, "latest_scan": dict(latest) if latest else None}


def safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip()
    return re.sub(r"\s+", "_", name)


def pattern_name(media: dict[str, Any], pattern: str, counter: int = 1) -> str:
    path = Path(media["full_path"])
    values = {
        "date": (media.get("modified_at") or now())[:10].replace("-", ""),
        "stem": path.stem,
        "original": Path(media.get("original_filename") or path.name).stem,
        "resolution": f"{media.get('width') or 'x'}x{media.get('height') or 'x'}",
        "duration": str(int(media.get("duration_seconds") or 0)),
        "codec": media.get("codec") or "codec",
        "project": media.get("project_name") or "project",
        "status": media.get("approval_status") or "needs-review",
        "counter": f"{counter:03d}",
        "ext": path.suffix.lstrip("."),
    }
    try:
        return safe_name(pattern.format(**values))
    except KeyError as exc:
        raise ValueError(f"Unknown rename token: {exc}")


def note_for(media: dict[str, Any], preset: str) -> str:
    title = media.get("current_filename", "media")
    if preset == "production":
        return f"## Production Notes\n\nFile: {title}\nProject: {media.get('project_name') or 'Unassigned'}\nStatus: {media.get('approval_status')}\n\nReview picture quality, audio clarity, best usable moments, and whether this clip belongs in edit, archive, or client review."
    if preset == "social":
        return f"## Social Clip Ideas\n\nUse {title} for a short hook, captioned highlight, behind-the-scenes moment, or client-facing teaser. Look for a 6-15 second section with clear action or emotion."
    if preset == "rename":
        return f"## Rename Suggestion\n\nSuggested pattern: Vollywood_{{date}}_{{project}}_{{stem}}_{{counter}}.{{ext}}"
    return f"## {preset.title()} Notes\n\nAdd review notes for {title}."


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str = "", status: str = ""):
    return templates.TemplateResponse("index.html", {"request": request, "media": list_media(q, status), "q": q, "status": status, "stats": stats(), "app_name": APP_NAME})


@app.post("/scan")
def scan(folder_path: str = Form(...), recursive: bool = Form(False), make_thumbnails: bool = Form(False)):
    scan_folder(folder_path, recursive, make_thumbnails)
    return RedirectResponse("/", status_code=303)


@app.get("/media/{media_id}", response_class=HTMLResponse)
def detail(request: Request, media_id: int):
    media = get_media(media_id)
    with db() as conn:
        history = [dict(r) for r in conn.execute("SELECT * FROM rename_history WHERE media_id=? ORDER BY id DESC LIMIT 20", (media_id,)).fetchall()]
        notes = [dict(r) for r in conn.execute("SELECT * FROM note_history WHERE media_id=? ORDER BY id DESC LIMIT 10", (media_id,)).fetchall()]
    return templates.TemplateResponse("detail.html", {"request": request, "media": media, "history": history, "note_history": notes, "app_name": APP_NAME})


@app.post("/media/{media_id}/update")
def update_media(media_id: int, project_name: str = Form(""), tags: str = Form(""), approval_status: str = Form("needs-review"), rating: int = Form(0), notes: str = Form("")):
    with db() as conn:
        conn.execute("UPDATE media_files SET project_name=?, tags=?, approval_status=?, rating=?, notes=? WHERE id=?", (project_name, tags, approval_status, rating, notes, media_id))
        conn.commit()
    return RedirectResponse(f"/media/{media_id}", status_code=303)


@app.post("/media/{media_id}/note")
def make_note(media_id: int, preset: str = Form("production"), append: bool = Form(True)):
    media = get_media(media_id)
    content = note_for(media, preset)
    new_notes = (media.get("notes") or "") + ("\n\n" if append and media.get("notes") else "") + content
    with db() as conn:
        conn.execute("UPDATE media_files SET notes=? WHERE id=?", (new_notes, media_id))
        conn.execute("INSERT INTO note_history (media_id,preset_key,content,generated_at) VALUES (?,?,?,?)", (media_id, preset, content, now()))
        conn.commit()
    return RedirectResponse(f"/media/{media_id}", status_code=303)


@app.post("/media/{media_id}/rename-preview")
def rename_preview(media_id: int, new_filename: str = Form(""), pattern: str = Form("")):
    media = get_media(media_id)
    target = pattern_name(media, pattern) if pattern else safe_name(new_filename)
    if not target:
        raise HTTPException(400, "Provide a filename or pattern")
    with db() as conn:
        conn.execute("UPDATE media_files SET suggested_filename=? WHERE id=?", (target, media_id))
        conn.commit()
    return RedirectResponse(f"/media/{media_id}", status_code=303)


@app.post("/media/{media_id}/rename-apply")
def rename_apply(media_id: int, new_filename: str = Form(""), pattern: str = Form("")):
    media = get_media(media_id)
    old_path = Path(media["full_path"])
    target_name = pattern_name(media, pattern) if pattern else safe_name(new_filename or media.get("suggested_filename") or "")
    if not target_name:
        raise HTTPException(400, "Provide a filename or pattern")
    new_path = old_path.with_name(target_name)
    if not old_path.exists():
        raise HTTPException(400, "Original file does not exist")
    if new_path.exists():
        raise HTTPException(400, "Target filename already exists")
    old_path.rename(new_path)
    with db() as conn:
        conn.execute("UPDATE media_files SET current_filename=?, full_path=?, folder_path=?, suggested_filename='' WHERE id=?", (new_path.name, str(new_path), str(new_path.parent), media_id))
        conn.execute("INSERT INTO rename_history (media_id,old_path,new_path,old_filename,new_filename,renamed_at,status,message) VALUES (?,?,?,?,?,?,?,?)", (media_id, str(old_path), str(new_path), old_path.name, new_path.name, now(), "renamed", "Safe rename applied"))
        conn.commit()
    return RedirectResponse(f"/media/{media_id}", status_code=303)


@app.get("/thumb/{filename}")
def thumb(filename: str):
    path = THUMBNAIL_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(path)


@app.get("/duplicates", response_class=HTMLResponse)
def duplicates(request: Request):
    with db() as conn:
        rows = conn.execute("SELECT fingerprint, COUNT(*) c FROM media_files WHERE fingerprint IS NOT NULL GROUP BY fingerprint HAVING c > 1 ORDER BY c DESC").fetchall()
        groups = []
        for row in rows:
            items = [dict(r) for r in conn.execute("SELECT * FROM media_files WHERE fingerprint=?", (row["fingerprint"],)).fetchall()]
            groups.append({"fingerprint": row["fingerprint"], "count": row["c"], "items": items})
    return templates.TemplateResponse("duplicates.html", {"request": request, "groups": groups, "app_name": APP_NAME})


@app.get("/export.csv")
def export_csv():
    rows = list_media()
    fields = ["id", "current_filename", "full_path", "project_name", "tags", "approval_status", "rating", "duration_seconds", "width", "height", "codec", "notes"]
    def generate():
        import io
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader(); yield out.getvalue(); out.seek(0); out.truncate(0)
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in fields}); yield out.getvalue(); out.seek(0); out.truncate(0)
    return StreamingResponse(generate(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=vollywood-media-index.csv"})


@app.get("/health")
def health():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}


@app.get("/api/media")
def api_media(q: str = "", status: str = ""):
    return {"media": list_media(q, status)}


@app.get("/api/media/{media_id}")
def api_media_detail(media_id: int):
    return get_media(media_id)
