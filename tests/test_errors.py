from pathlib import Path
import logging
from gamecat.exceptions import GameCATError, ImportFormatError, DatabaseError
from gamecat.logging_config import configure_logging


def test_domain_error_types():
    assert issubclass(ImportFormatError, GameCATError)
    assert issubclass(DatabaseError, GameCATError)


def test_logging_writes_file(tmp_path: Path):
    path=tmp_path/'gamecat.log'
    configure_logging(path)
    logging.getLogger('gamecat.test').error('boom')
    for h in logging.getLogger().handlers:
        try: h.flush()
        except Exception: pass
    assert 'boom' in path.read_text(encoding='utf-8')
