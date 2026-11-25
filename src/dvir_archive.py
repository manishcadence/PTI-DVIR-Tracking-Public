"""Durable rolling-report imports, inspection history and consistent SQLite backups."""
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd

from .equipment import equipment_summary
from .normalization import normalize


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS imports (
            digest TEXT PRIMARY KEY, imported_at TEXT NOT NULL, source TEXT NOT NULL,
            raw_json BLOB NOT NULL, backed_up INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS drivers (
            driver_id TEXT PRIMARY KEY, driver_name TEXT, last_seen TEXT);
        CREATE TABLE IF NOT EXISTS events (
            event_key TEXT PRIMARY KEY, driver_id TEXT, inspection_time TEXT,
            first_seen TEXT, last_seen TEXT, event_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS events_driver_time ON events(driver_id, inspection_time);
        CREATE TABLE IF NOT EXISTS roster_snapshots (
            digest TEXT REFERENCES imports(digest), source_row INTEGER, driver_id TEXT,
            roster_json TEXT NOT NULL, PRIMARY KEY(digest, source_row));
        CREATE TABLE IF NOT EXISTS import_events (
            digest TEXT REFERENCES imports(digest), event_key TEXT REFERENCES events(event_key),
            event_json TEXT NOT NULL, PRIMARY KEY(digest, event_key));
    ''')
    return conn


def backup_database(path, destination):
    """SQLite backup API gives a consistent copy while the dashboard is running."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as file:
        temporary = Path(file.name)
    try:
        with closing(sqlite3.connect(str(path), timeout=30)) as source:
            with closing(sqlite3.connect(str(temporary))) as target:
                source.backup(target)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _stamp(value):
    return None if pd.isna(value) else value.isoformat()


def archive_report(path, backup_dir, envelope, source, raw_json=None, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    # Reformatting the same JSON should not create another import.
    payload = json.loads(raw_json) if raw_json is not None else envelope.model_dump(mode='json')
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    backup_path = Path(backup_dir) / f'dvir-history-{now:%Y-%m-%d}.sqlite3'
    with closing(connect(path)) as conn:
        conn.execute('BEGIN IMMEDIATE')  # Serialize identical first imports across dashboard sessions.
        existing = conn.execute('SELECT backed_up FROM imports WHERE digest=?', (digest,)).fetchone()
        if existing is None:
            data = normalize(envelope, 'UTC')
            equipment = equipment_summary(data.dvir_records, data.source_rows or None).set_index('driver_id')
            occurrences = defaultdict(int)
            events = {}
            for row in data.dvir_records.itertuples(index=False):
                raw = row.raw if isinstance(row.raw, dict) else {}
                grouped = raw.get('sourceFormat') == 'groupedDriver'
                start, end = _stamp(row.start_time), _stamp(row.end_time)
                if grouped:
                    # Array-level generated IDs change when a rolling export changes.
                    # Match timestamp pairs across imports; retain repeated pairs by occurrence.
                    source_row = raw.get('groupedSource', {})
                    history = json.dumps([source_row.get('startTimes'), source_row.get('endTimes')])
                    pair = (row.author_id, start, end)
                    occurrences[(history, pair)] += 1
                    identity = [*pair, occurrences[(history, pair)]]
                    if start is None and end is None:
                        identity += [digest, row.dvir_id]
                    key = 'grouped:' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                else:
                    key = 'dvir:' + row.dvir_id
                info = {
                    'history_id': key, 'dvir_id': None if grouped else row.dvir_id,
                    'driver_id': row.author_id, 'driver_name': row.author_name,
                    'inspection_time': _stamp(row.inspection_time), 'start_time': start, 'end_time': end,
                    'inspection_type': row.inspection_type,
                    'vehicle_names_in_report': equipment.loc[row.author_id, 'vehicle_names']
                        if row.author_id in equipment.index else 'Not supplied',
                    'vehicle_id': row.vehicle_id, 'trailer_id': row.trailer_id,
                    'vehicle_ids_in_report': equipment.loc[row.author_id, 'vehicle_ids']
                        if row.author_id in equipment.index else 'Not supplied',
                    'trailer_names_in_report': equipment.loc[row.author_id, 'trailer_names']
                        if row.author_id in equipment.index else 'Not supplied',
                    'trailer_ids_in_report': equipment.loc[row.author_id, 'trailer_ids']
                        if row.author_id in equipment.index else 'Not supplied',
                    'safety_status': row.safety_status,
                    'trip_types_in_report': raw.get('groupedSource', {}).get('tripTypes', [])
                        if grouped else [row.inspection_type],
                    'reported_defects': None if grouped else row.total_defects,
                    'matching_basis': 'driver_timestamp_pair_occurrence' if grouped else 'samsara_dvir_id',
                    'status_scope': 'grouped_source_not_verified_per_event' if grouped else 'inspection',
                }
                events[key] = info
            with conn:
                conn.execute('INSERT INTO imports(digest,imported_at,source,raw_json) VALUES (?,?,?,?)',
                             (digest, stamp, source, gzip.compress(canonical)))
                for number, source_row in enumerate(data.source_rows, 1):
                    if source_row.get('_roster_driver_id'):
                        conn.execute('INSERT INTO roster_snapshots VALUES (?,?,?,?)',
                                     (digest, number, source_row['_roster_driver_id'], json.dumps(source_row)))
                for row in data.drivers.itertuples(index=False):
                    conn.execute('''INSERT INTO drivers VALUES (?,?,?) ON CONFLICT(driver_id)
                        DO UPDATE SET driver_name=excluded.driver_name,last_seen=excluded.last_seen''',
                        (row.driver_id, row.driver_name, stamp))
                for author in data.dvir_records.dropna(subset=['author_id']).drop_duplicates('author_id').itertuples(index=False):
                    conn.execute('INSERT OR IGNORE INTO drivers VALUES (?,?,?)', (author.author_id,author.author_name,stamp))
                for key, info in events.items():
                    event_json = json.dumps(info, ensure_ascii=False)
                    conn.execute('''INSERT INTO events VALUES (?,?,?,?,?,?) ON CONFLICT(event_key)
                        DO UPDATE SET driver_id=excluded.driver_id,inspection_time=excluded.inspection_time,
                        last_seen=excluded.last_seen,event_json=excluded.event_json''',
                        (key, info['driver_id'], info['inspection_time'], stamp, stamp, event_json))
                    conn.execute('INSERT INTO import_events VALUES (?,?,?)', (digest, key, event_json))
        if existing is None or not existing[0] or not backup_path.exists():
            backup_database(path, backup_path)
            with conn:
                conn.execute('UPDATE imports SET backed_up=1 WHERE digest=?', (digest,))
    return digest


def archive_stats(path):
    with closing(connect(path)) as conn:
        return {'drivers': conn.execute('SELECT COUNT(*) FROM drivers').fetchone()[0],
                'events': conn.execute('SELECT COUNT(*) FROM events').fetchone()[0],
                'imports': conn.execute('SELECT COUNT(*) FROM imports').fetchone()[0],
                'last_import': conn.execute('SELECT MAX(imported_at) FROM imports').fetchone()[0]}


def history_rows(path):
    with closing(connect(path)) as conn:
        rows = conn.execute('SELECT event_json,first_seen,last_seen FROM events ORDER BY inspection_time DESC').fetchall()
    return pd.DataFrame([{**json.loads(payload), 'first_seen': first, 'last_seen': last}
                         for payload, first, last in rows])


def import_rows(path):
    with closing(connect(path)) as conn:
        return pd.read_sql_query('SELECT imported_at,source,digest FROM imports ORDER BY imported_at DESC', conn)


def sqlite_download(path):
    with tempfile.TemporaryDirectory() as directory:
        return backup_database(path, Path(directory) / 'history.sqlite3').read_bytes()


def json_download(path):
    output = BytesIO()
    with closing(connect(path)) as conn, ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for digest, imported_at, payload in conn.execute('SELECT digest,imported_at,raw_json FROM imports'):
            safe_time = imported_at.replace(':', '-')
            archive.writestr(f'{safe_time}-{digest[:12]}.json', gzip.decompress(payload))
    return output.getvalue()
