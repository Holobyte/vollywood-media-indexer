from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.ai_notes import local_note
from app.main import app, pattern_name, safe_name

client = TestClient(app)


def test_health_page_returns_ok() -> None:
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['app'] == 'Vollywood Media Indexer'


def test_home_page_loads() -> None:
    response = client.get('/')
    assert response.status_code == 200
    assert 'Media Index' in response.text


def test_ai_page_loads() -> None:
    response = client.get('/ai')
    assert response.status_code == 200
    assert 'AI Notes' in response.text


def test_duplicates_page_loads() -> None:
    response = client.get('/duplicates')
    assert response.status_code == 200
    assert 'Duplicate Candidates' in response.text


def test_safe_name_removes_problem_characters() -> None:
    assert safe_name('Client Shoot: Take #1.mov') == 'Client_Shoot_Take_1.mov'


def test_pattern_name_basic_tokens() -> None:
    media = {
        'full_path': str(Path('/tmp/example clip.mp4')),
        'modified_at': '2026-07-03T12:00:00',
        'original_filename': 'example clip.mp4',
        'width': 1920,
        'height': 1080,
        'duration_seconds': 12.5,
        'codec': 'h264',
        'project_name': 'Demo',
        'approval_status': 'needs-review',
    }
    result = pattern_name(media, 'Vollywood_{date}_{project}_{resolution}_{counter}.{ext}')
    assert result == 'Vollywood_20260703_Demo_1920x1080_001.mp4'


def test_local_note_contains_file_context() -> None:
    media = {'current_filename': 'clip.mp4', 'project_name': 'Demo', 'approval_status': 'needs-review'}
    note = local_note(media, 'production')
    assert 'clip.mp4' in note
    assert 'Demo' in note
