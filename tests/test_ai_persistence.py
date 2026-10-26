from pathlib import Path

import pytest

from gamecat.ai.core import AISettings
from gamecat.services.project_service import ProjectService
from gamecat.models.segment import Segment, SegmentStatus


def test_settings_roundtrip_and_reopen_without_secret(tmp_path: Path):
    db = tmp_path / 'p.sqlite'
    service = ProjectService(db)
    project = service.create_project('Demo', 'en', 'pl', 'json')
    cfg = AISettings(model='gpt-5-mini', instructions='Terminologia fantasy', input_price_per_million=1,
                     output_price_per_million=2, max_output_tokens=500)
    service.set_ai_settings(project, cfg)
    service.close()
    other = ProjectService(db)
    saved = other.get_ai_settings(project)
    assert saved.model == 'gpt-5-mini'
    assert saved.instructions == 'Terminologia fantasy'
    assert saved.max_output_tokens == 500
    assert 'api_key' not in str(other.connection.execute('SELECT sql FROM sqlite_master').fetchall())
    other.close()


def test_ai_apply_requires_consent_and_preserves_source(tmp_path: Path):
    service = ProjectService(tmp_path / 'p.sqlite')
    p = service.create_project('X', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Sword {name}', 1, target='Poprzedni', status=SegmentStatus.REVIEWED, project_id=p.id))
    with pytest.raises(ValueError):
        service.apply_ai_translation(p, segment.id, 'Miecz {name}', 'gpt-5-mini')
    with pytest.raises(ValueError):
        service.apply_ai_translation(p, segment.id, 'Miecz {name}', 'gpt-5-mini', replace=True)
    service.apply_ai_translation(p, segment.id, 'Miecz {name}', 'gpt-5-mini', replace=True, include_reviewed=True)
    current = service.list_segments(p.id)[0]
    assert current.source == 'Sword {name}'
    assert current.target == 'Miecz {name}'
    assert current.status is SegmentStatus.TRANSLATED
    assert current.ai_generated
    current.target = 'Ręczna korekta'
    current.ai_generated = False
    service.save_segment(current)
    assert not service.list_segments(p.id)[0].ai_generated
    service.close()


def test_ai_apply_detects_stale_source_and_target(tmp_path: Path):
    service = ProjectService(tmp_path / 'p.sqlite')
    p = service.create_project('X', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Source', 1, project_id=p.id))
    with pytest.raises(ValueError):
        service.apply_ai_translation(p, segment.id, 'Tekst', 'gpt-5-mini', expected_source='Old')
    with pytest.raises(ValueError):
        service.apply_ai_translation(p, segment.id, 'Tekst', 'gpt-5-mini', expected_target='Old')
    assert service.list_segments(p.id)[0].target == ''
    service.close()
