from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

SYSTEM_PROMPT = (
    "You are a post-production assistant for Vollywood. "
    "Write practical production notes for editors, producers, and clients. "
    "Do not claim to have watched the video unless transcript or visual notes are provided. "
    "Base the answer only on the metadata, filename, project notes, tags, and user prompt."
)

PRESET_PROMPTS = {
    "production": "Create structured production notes with likely use, review concerns, edit value, and next action.",
    "social": "Create short-form social clip ideas, hooks, captions, and vertical video suggestions.",
    "rename": "Suggest safe production filenames and a naming pattern using the available metadata.",
    "review": "Create client review notes with clear approval questions and revision checklist.",
    "broll": "Suggest possible B-roll categories, edit uses, and archive tags.",
    "archive": "Create archive notes with library tags, project grouping, and future retrieval keywords.",
}


def media_context(media: dict[str, Any]) -> str:
    return "\n".join([
        f"Filename: {media.get('current_filename')}",
        f"Original filename: {media.get('original_filename')}",
        f"Project: {media.get('project_name') or 'Unassigned'}",
        f"Tags: {media.get('tags') or 'None'}",
        f"Status: {media.get('approval_status') or 'needs-review'}",
        f"Rating: {media.get('rating') or 0}/5",
        f"Duration seconds: {media.get('duration_seconds') or 'Unknown'}",
        f"Resolution: {media.get('width') or 'Unknown'}x{media.get('height') or 'Unknown'}",
        f"Codec: {media.get('codec') or 'Unknown'}",
        f"Frame rate: {media.get('frame_rate') or 'Unknown'}",
        f"Existing notes: {media.get('notes') or 'None'}",
    ])


def local_note(media: dict[str, Any], preset: str, custom_prompt: str = "") -> str:
    title = media.get("current_filename", "media")
    project = media.get("project_name") or "Unassigned"
    base = PRESET_PROMPTS.get(preset, "Create practical review notes for this media file.")
    custom = f"\n\nCustom direction: {custom_prompt}" if custom_prompt else ""
    return (
        f"## {preset.title()} Notes\n\n"
        f"File: {title}\n"
        f"Project: {project}\n"
        f"Status: {media.get('approval_status') or 'needs-review'}\n"
        f"Technical: {media.get('duration_seconds') or 'Unknown'} sec, "
        f"{media.get('width') or 'Unknown'}x{media.get('height') or 'Unknown'}, "
        f"codec {media.get('codec') or 'Unknown'}\n\n"
        f"Task: {base}{custom}\n\n"
        "Suggested next steps:\n"
        "1. Watch the clip and mark the best usable timecodes.\n"
        "2. Confirm audio quality, visual quality, and client relevance.\n"
        "3. Add stronger tags after review.\n"
        "4. Move approved clips into the correct project workflow."
    )


def build_prompt(media: dict[str, Any], preset: str, custom_prompt: str = "") -> str:
    preset_prompt = PRESET_PROMPTS.get(preset, "Create practical media review notes.")
    return (
        "Create production-ready notes for this indexed video file.\n\n"
        f"Preset task: {preset_prompt}\n\n"
        f"Media context:\n{media_context(media)}\n\n"
        f"User custom direction: {custom_prompt or 'None'}\n\n"
        "Return concise markdown with sections for: Summary, Best Use, Edit Ideas, Tags, Rename Suggestion, and Next Action."
    )


def ai_note(media: dict[str, Any], preset: str, custom_prompt: str = "") -> tuple[str, str]:
    provider = os.getenv("VMI_AI_PROVIDER", "local").strip().lower()
    if provider in ("", "local", "none"):
        return local_note(media, preset, custom_prompt), "local"
    if provider not in ("openai", "openai-compatible"):
        return local_note(media, preset, custom_prompt), f"local-fallback-unknown-provider-{provider}"

    api_key = os.getenv("VMI_OPENAI_API_KEY", "").strip()
    if not api_key:
        return local_note(media, preset, custom_prompt), "local-fallback-missing-api-key"

    base_url = os.getenv("VMI_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("VMI_OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(media, preset, custom_prompt)},
        ],
        "temperature": 0.35,
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        return content, f"openai-compatible:{model}"
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
        fallback = local_note(media, preset, custom_prompt)
        return fallback + f"\n\nAI provider failed, used local fallback. Error: {exc}", "local-fallback-provider-error"
