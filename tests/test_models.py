import pytest
from gamecat.models.project import Project
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.models.glossary import GlossaryEntry
from gamecat.models.translation_memory import TranslationMemoryEntry


def test_project_creation():
    p = Project(name='Demo', source_language='en', target_language='pl', source_format='txt')
    assert p.name == 'Demo'
    assert p.source_language == 'en'
    assert p.target_language == 'pl'


def test_segment_defaults_and_target_property():
    s = Segment(source='Hello', position=1)
    assert s.status is SegmentStatus.NEW
    assert s.target == ''
    s.target = 'Cześć'
    assert s.target == 'Cześć'
    with pytest.raises(TypeError):
        s.target = 123  # type: ignore[assignment]


def test_segment_status_accepts_enum_and_string():
    s = Segment(source='Hello', position=1)
    s.status = SegmentStatus.TRANSLATED
    assert s.status is SegmentStatus.TRANSLATED
    s.status = 'REVIEWED'
    assert s.status is SegmentStatus.REVIEWED
    with pytest.raises(ValueError):
        s.status = 'INVALID'


def test_glossary_and_tm_models():
    g = GlossaryEntry(source_term='quest', target_term='zadanie')
    tm = TranslationMemoryEntry(source='Quest complete', target='Zadanie ukończone', source_language='en', target_language='pl')
    assert g.case_sensitive is False
    assert tm.origin_project is None
