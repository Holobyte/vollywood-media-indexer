# Setup

This is a local FastAPI app for indexing video production folders.

## Run

1. Create and activate a Python virtual environment.
2. Install dependencies from requirements.txt.
3. Start the app with uvicorn app.main:app --reload.
4. Open http://127.0.0.1:8000 in your browser.

## Recommended

Install FFmpeg so the app can read video metadata and create thumbnails.

## Safety

The app runs locally. It does not upload video files. Rename actions are checked before applying and will not overwrite existing files.
