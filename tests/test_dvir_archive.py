from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
import sqlite3
from zipfile import ZipFile

from src.data_adapter import adapt
from src.dvir_archive import archive_report, archive_stats, history_rows, json_download, sqlite_download


def test_native_updates_overlap_retention_and_restorable_downloads(tmp_path, dvir):
    path, backups = tmp_path / 'history.sqlite3', tmp_path / 'backups'
    second = deepcopy(dvir)
    second['id'] = 'X2'
    first_payload = {'data': [dvir, second]}
    first = adapt(first_payload)
    now = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
    archive_report(path, backups, first, 'report.json', json.dumps(first_payload), now)
    archive_report(path, backups, first, 'report.json', json.dumps(first_payload, indent=2), now)
    assert archive_stats(path)['imports'] == 1
    changed = deepcopy(dvir)
    changed['safetyStatus'] = 'resolved'
    later_payload = {'data': [changed]}
    archive_report(path, backups, adapt(later_payload), 'report.json', json.dumps(later_payload), now)
    stats = archive_stats(path)
    assert stats['events'] == 2 and stats['imports'] == 2
    rows = history_rows(path).set_index('dvir_id')
    assert rows.loc['X1', 'safety_status'] == 'resolved'
    assert 'X2' in rows.index  # No longer in the latest rolling report, still in history.
    with sqlite3.connect(path) as conn:
        revisions = conn.execute("SELECT COUNT(*) FROM import_events WHERE event_key='dvir:X1'").fetchone()[0]
        assert revisions == 2
    with ZipFile(BytesIO(json_download(path))) as archive:
        assert len(archive.namelist()) == 2
        contents = [json.loads(archive.read(name)) for name in archive.namelist()]
        assert first_payload in contents and later_payload in contents
    restored = tmp_path / 'restore.sqlite3'
    restored.write_bytes(sqlite_download(path))
    assert archive_stats(restored)['events'] == 2
    backup = backups / 'dvir-history-2026-11-18.sqlite3'
    assert backup.exists()
    with sqlite3.connect(backup) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 2


def test_grouped_rolling_arrays_match_events_without_losing_old_days(tmp_path):
    path, backups = tmp_path / 'history.sqlite3', tmp_path / 'backups'
    row = {'driverID': 'D1', 'driverName': 'Alex', 'totalPTI': 2,
           'startTimes': ['2026-11-01T12:00:00Z', '2026-11-02T12:00:00Z'],
           'endTimes': ['2026-11-01T12:10:00Z', '2026-11-02T12:10:00Z'],
           'tripTypes': ['preTrip'], 'vehicleNames': ['One', 'Two'], 'safetyStatuses': ['safe']}
    archive_report(path, backups, adapt([row, row]), 'grouped.json')
    assert archive_stats(path)['events'] == 2
    later = deepcopy(row)
    later['startTimes'] = ['2026-11-02T06:00:00-06:00', '2026-11-03T12:00:00Z']
    later['endTimes'] = ['2026-11-02T06:10:00-06:00', '2026-11-03T12:10:00Z']
    archive_report(path, backups, adapt([later]), 'grouped.json')
    assert archive_stats(path)['events'] == 3
    history = history_rows(path)
    assert history.matching_basis.eq('driver_timestamp_pair_occurrence').all()
    assert history.dvir_id.isna().all()
    assert history.vehicle_names_in_report.eq('One, Two').all()


def test_repeated_timestamp_pairs_within_group_preserve_occurrences(tmp_path):
    row = {'driverID': 'D1', 'totalPTI': 2,
           'startTimes': ['2026-11-01T12:00:00Z'] * 2, 'endTimes': [None] * 2,
           'tripTypes': ['preTrip']}
    path = tmp_path / 'history.sqlite3'
    archive_report(path, tmp_path / 'backups', adapt([row]), 'grouped.json')
    assert archive_stats(path)['events'] == 2
    later = deepcopy(row)
    later['startTimes'].append('2026-11-02T12:00:00Z')
    later['endTimes'].append(None)
    later['totalPTI'] = 3
    archive_report(path, tmp_path / 'backups', adapt([later]), 'grouped.json')
    assert archive_stats(path)['events'] == 3



def test_concurrent_imports_do_not_duplicate_or_fail(tmp_path,dvir):
    from concurrent.futures import ThreadPoolExecutor
    path=tmp_path/'history.sqlite3'
    envelope=adapt({'data':[dvir]})
    def ingest(_):
        return archive_report(path,tmp_path/'backups',envelope,'same.json')
    with ThreadPoolExecutor(max_workers=2) as pool:
        digests=list(pool.map(ingest,range(2)))
    assert digests[0]==digests[1]
    assert archive_stats(path)['imports']==1
    assert archive_stats(path)['events']==1
