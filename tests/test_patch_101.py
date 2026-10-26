"""Regression checks for GameCAT 1.0.1 stability fixes."""
from __future__ import annotations

import threading
from pathlib import Path

from gamecat.database.connection import open_database
from gamecat.models.segment import SegmentStatus
from gamecat.workflow.status import status_after_target_edit


def test_editing_reviewed_text_invalidates_review_only_on_real_change():
    assert status_after_target_edit(SegmentStatus.APPROVED, 'Stary', 'Nowy') is SegmentStatus.TRANSLATED
    assert status_after_target_edit(SegmentStatus.REVIEWED, 'Stary', 'Nowy') is SegmentStatus.TRANSLATED
    assert status_after_target_edit(SegmentStatus.APPROVED, 'Stary', 'Stary') is SegmentStatus.APPROVED
    assert status_after_target_edit(SegmentStatus.NEW, '', 'Nowy') is SegmentStatus.TRANSLATED
    assert status_after_target_edit(SegmentStatus.APPROVED, 'Stary', '') is SegmentStatus.NEW
    assert status_after_target_edit(SegmentStatus.TRANSLATED, 'Stary', '') is SegmentStatus.NEW


def test_shared_connection_does_not_read_rolled_back_changes(tmp_path: Path):
    conn = open_database(tmp_path / 'sharing.sqlite')
    conn.execute('CREATE TABLE t (value TEXT)')
    conn.commit()
    inserted = threading.Event()
    release = threading.Event()
    read_started = threading.Event()
    read_finished = threading.Event()
    observed = []

    def writer():
        try:
            with conn:
                conn.execute('INSERT INTO t VALUES (?)', ('uncommitted',))
                inserted.set()
                assert release.wait(5)
                raise RuntimeError('rollback on purpose')
        except RuntimeError:
            pass

    def reader():
        assert inserted.wait(5)
        read_started.set()
        observed.append(conn.fetchone('SELECT COUNT(*) FROM t')[0])
        read_finished.set()

    tw = threading.Thread(target=writer)
    tr = threading.Thread(target=reader)
    tw.start(); tr.start()
    try:
        assert read_started.wait(5)
        assert not read_finished.wait(0.15), 'Reader must wait until writer transaction finishes'
    finally:
        release.set()
        tw.join(timeout=5)
        tr.join(timeout=5)
        conn.close()
    assert not tw.is_alive() and not tr.is_alive()
    assert observed == [0]


def test_execute_waits_for_other_thread_transaction(tmp_path: Path):
    conn = open_database(tmp_path / 'execute.sqlite')
    conn.execute('CREATE TABLE t (value TEXT)')
    conn.commit()
    inserted = threading.Event()
    release = threading.Event()
    reached = threading.Event()
    completed = threading.Event()
    result = []

    def writer():
        with conn:
            conn.execute('INSERT INTO t VALUES (?)', ('commit',))
            inserted.set()
            assert release.wait(5)

    def reader():
        assert inserted.wait(5)
        reached.set()
        result.append(conn.execute('SELECT COUNT(*) FROM t').fetchone()[0])
        completed.set()

    tw = threading.Thread(target=writer)
    tr = threading.Thread(target=reader)
    tw.start(); tr.start()
    try:
        assert reached.wait(5)
        assert not completed.wait(0.15), 'Concurrent execute cannot enter a foreign transaction'
    finally:
        release.set()
        tw.join(timeout=5)
        tr.join(timeout=5)
        conn.close()
    assert not tw.is_alive() and not tr.is_alive()
    assert result == [1]
