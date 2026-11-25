"""Import training exports and retain their history in a local SQLite database."""
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sqlite3

import pandas as pd

from .data_adapter import Envelope, identifier


HEADERS = ['SamsaraDriverID', 'SamsaraDriverName', 'SamsaraState', 'PTI',
           'MondayJoinDate', 'PTITrainingDate', 'MondayPhone', 'DriverID',
           'MondayNamne', 'SamsaraPhoneNumber', 'SamsaraELDID']
STATUSES = {
    'completed': 'completed', 'complete': 'completed', 'done': 'completed',
    'trained': 'completed', 'incomplete': 'incomplete', 'not done': 'incomplete',
    'not trained': 'not_trained', 'not_trained': 'not_trained', 'unknown': 'unknown',
}


def parse_training(contents: bytes, filename: str) -> list[dict]:
    """Read text as strings to preserve IDs and phone numbers; never execute formulas."""
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        frame = pd.read_csv(BytesIO(contents), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    elif suffix in {'.xls', '.xlsx'}:
        frame = pd.read_excel(BytesIO(contents), dtype=str, keep_default_na=False,
                              engine='xlrd' if suffix == '.xls' else 'openpyxl')
    elif suffix == '.json':
        rows = json.loads(contents)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError('Training JSON must be an array of row objects.')
        frame = pd.DataFrame(rows).fillna('')
    else:
        raise ValueError('Use a CSV, XLS, XLSX, or JSON training file.')
    frame.columns = [str(column).strip() for column in frame.columns]
    if frame.columns.duplicated().any():
        raise ValueError('Training column names must be unique.')
    required = {'SamsaraDriverID', 'PTI', 'PTITrainingDate'}
    if not required.issubset(frame.columns):
        raise ValueError('Training file requires SamsaraDriverID, PTI, and PTITrainingDate columns.')
    if frame.empty:
        raise ValueError('The training file has headers but no driver rows.')
    return [{str(key): str(value).strip() if value is not None else ''
             for key, value in row.items()} for row in frame.to_dict('records')]


def training_values(row: dict) -> tuple[str, str | None]:
    status = STATUSES.get(row.get('PTI', '').strip().lower(), 'unknown')
    raw_date = row.get('PTITrainingDate', '').strip()
    completed_at = None
    if status == 'completed' and raw_date:
        # ISO dates and offset timestamps avoid ambiguous month/day interpretation.
        parsed = pd.to_datetime(raw_date, errors='coerce', utc=True, format='ISO8601')
        if pd.notna(parsed):
            completed_at = parsed.date().isoformat() if len(raw_date) == 10 or raw_date.endswith(' 00:00:00') else parsed.isoformat()
    return status, completed_at


def summarize_training(rows: list[dict]) -> dict[str, dict]:
    result = {}
    conflicts = set()
    for row in rows:
        driver_id = identifier(row.get('SamsaraDriverID'))
        if not driver_id:
            continue
        value = dict(zip(('training_status', 'training_completed_at'), training_values(row)))
        if driver_id in result and result[driver_id] != value:
            conflicts.add(driver_id)
        result[driver_id] = value
    for driver_id in conflicts:
        result[driver_id] = {'training_status': 'unknown', 'training_completed_at': None}
    return result


def save_training(path: str, filename: str, contents: bytes, rows: list[dict]) -> None:
    """Save original export and per-driver history atomically. Later uploads update included IDs."""
    if not summarize_training(rows):
        raise ValueError('No SamsaraDriverID values were supplied; no records were saved.')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as connection, connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS training_imports (
            id INTEGER PRIMARY KEY, filename TEXT, imported_at TEXT, original BLOB, rows_json TEXT)''')
        connection.execute('INSERT INTO training_imports (filename, imported_at, original, rows_json) VALUES (?, ?, ?, ?)',
                           (Path(filename).name, datetime.now(timezone.utc).isoformat(), contents, json.dumps(rows)))


def load_training(path: str) -> tuple[dict[str, dict], str | None]:
    if not Path(path).exists():
        return {}, None
    saved, latest = {}, None
    with closing(sqlite3.connect(path, timeout=5)) as connection:
        for timestamp, raw in connection.execute('SELECT imported_at, rows_json FROM training_imports ORDER BY id'):
            saved.update(summarize_training(json.loads(raw)))
            latest = timestamp
    return saved, latest


def merge_training(envelope: Envelope, saved: dict[str, dict]) -> Envelope:
    """Local saved records override webhook training only for matching stable driver IDs."""
    if not saved:
        return envelope
    result = envelope.model_copy(deep=True)
    known = set()
    for row in result.drivers:
        driver_id = identifier(row.get('id', row.get('driver_id')))
        known.add(driver_id)
        if driver_id in saved:
            row.update(saved[driver_id])
    for inspection in result.inspections:
        signature = inspection.get('authorSignature') or {}
        author = signature.get('signatoryUser') or {}
        driver_id = identifier(author.get('id'))
        if driver_id in saved and driver_id not in known:
            result.drivers.append({'id': driver_id, 'name': author.get('name'), **saved[driver_id]})
            known.add(driver_id)
    return result
