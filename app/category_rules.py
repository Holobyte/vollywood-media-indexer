from __future__ import annotations

from typing import Any


def suggest_categories(media: dict[str, Any], transcript_text: str = "") -> list[dict[str, Any]]:
    text = " ".join([
        media.get("current_filename") or "",
        media.get("folder_path") or "",
        media.get("project_name") or "",
        media.get("tags") or "",
        media.get("notes") or "",
        transcript_text or "",
    ]).lower()
    width = int(media.get("width") or 0)
    height = int(media.get("height") or 0)
    duration = float(media.get("duration_seconds") or 0)
    rules = [
        ("category", "interview/talking-head", 0.82, "Text suggests interview or talking-head footage.", ["interview", "talking head", "speaker", "mic", "podcast", "host", "guest"]),
        ("category", "b-roll", 0.78, "Text suggests B-roll or cutaway use.", ["broll", "b-roll", "cutaway", "establishing", "detail shot", "beauty shot"]),
        ("category", "drone/aerial", 0.86, "Text suggests aerial footage.", ["drone", "aerial", "dji", "flyover"]),
        ("category", "event-recap", 0.74, "Text suggests event coverage.", ["event", "recap", "conference", "workshop", "gala", "ceremony", "live"]),
        ("category", "real-estate", 0.82, "Text suggests property, listing, or real estate media.", ["real estate", "listing", "home", "house", "property", "realtor", "kitchen", "bedroom"]),
        ("category", "music-video", 0.78, "Text suggests music video, performance, or artist content.", ["music video", "artist", "performance", "song", "singer", "rapper", "band"]),
        ("category", "training-course", 0.76, "Text suggests educational or training material.", ["training", "lesson", "module", "course", "tutorial", "workshop"]),
    ]
    suggestions: list[dict[str, Any]] = []
    for suggestion_type, value, confidence, reason, keywords in rules:
        if any(keyword in text for keyword in keywords):
            suggestions.append({"suggestion_type": suggestion_type, "value": value, "confidence": confidence, "reason": reason})
    if width and height:
        if height > width:
            suggestions.append({"suggestion_type": "format", "value": "vertical/social", "confidence": 0.9, "reason": "Video height is greater than width."})
        elif width >= 3840:
            suggestions.append({"suggestion_type": "format", "value": "4k-master", "confidence": 0.86, "reason": "Resolution appears to be 4K or larger."})
        elif width >= 1920:
            suggestions.append({"suggestion_type": "format", "value": "hd-master", "confidence": 0.75, "reason": "Resolution appears to be HD."})
    if duration:
        if duration <= 20:
            suggestions.append({"suggestion_type": "use", "value": "short-clip-candidate", "confidence": 0.72, "reason": "Short duration makes this useful for reels, ads, or cutdowns."})
        elif duration >= 900:
            suggestions.append({"suggestion_type": "use", "value": "long-form-source", "confidence": 0.76, "reason": "Long duration suggests full source recording."})
    if not suggestions:
        suggestions.append({"suggestion_type": "review", "value": "manual-review-needed", "confidence": 0.35, "reason": "Not enough evidence to categorize confidently."})
    return suggestions
