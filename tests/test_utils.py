import pytest
from gamecat.utils.decorators import measure_time, retry, requires_project


def test_measure_time_preserves_metadata():
    @measure_time
    def sample(x):
        "doc"
        return x + 1
    assert sample.__name__ == 'sample'
    assert sample.__doc__ == 'doc'
    assert sample(2) == 3


def test_retry_uses_configured_attempts():
    calls = {'n': 0}
    @retry(attempts=3)
    def flaky():
        calls['n'] += 1
        if calls['n'] < 3:
            raise ValueError('x')
        return 'ok'
    assert flaky() == 'ok'
    assert calls['n'] == 3


def test_requires_project_uses_self():
    class C:
        current_project = None
        @requires_project
        def run(self): return 7
    with pytest.raises(RuntimeError, match='No project is open'):
        C().run()
    c = C(); c.current_project = object(); assert c.run() == 7


def test_retry_only_retries_selected_exceptions():
    calls = {'n': 0}

    @retry(attempts=3, exceptions=(ConnectionError,))
    def broken():
        calls['n'] += 1
        raise ValueError('not transient')

    with pytest.raises(ValueError):
        broken()
    assert calls['n'] == 1


def test_retry_predicate_filters_errors():
    import sqlite3
    from gamecat.utils.decorators import is_transient_sqlite_error
    calls = {'n': 0}

    @retry(attempts=3, exceptions=(sqlite3.OperationalError,), when=is_transient_sqlite_error)
    def locked_then_ok():
        calls['n'] += 1
        if calls['n'] == 1:
            raise sqlite3.OperationalError('database is locked')
        return 'ok'

    @retry(attempts=3, exceptions=(sqlite3.OperationalError,), when=is_transient_sqlite_error)
    def missing_table():
        calls['n'] += 1
        raise sqlite3.OperationalError('no such table: x')

    assert locked_then_ok() == 'ok' and calls['n'] == 2
    calls['n'] = 0
    with pytest.raises(sqlite3.OperationalError):
        missing_table()
    assert calls['n'] == 1


def test_retry_reraises_last_error_after_all_attempts():
    @retry(attempts=2, exceptions=(OSError,))
    def always():
        raise OSError('boom')
    with pytest.raises(OSError, match='boom'):
        always()


def test_measure_time_logs_duration(caplog):
    import logging

    @measure_time
    def work():
        return 1

    with caplog.at_level(logging.INFO, logger='gamecat.timing'):
        work()
    assert any('work' in r.getMessage() and ' s' in r.getMessage() for r in caplog.records)


def test_requires_project_checks_service_too():
    from gamecat.exceptions import NoProjectError

    class C:
        current_project = object()
        project_service = None

        @requires_project
        def run(self):
            return 1

    with pytest.raises(NoProjectError):
        C().run()
