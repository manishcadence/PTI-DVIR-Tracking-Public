import json
import sqlite3

import pytest

from src.data_adapter import adapt
from src.normalization import normalize
from src.training_store import load_training, merge_training, parse_training, save_training, summarize_training


CSV = b'SamsaraDriverID,SamsaraDriverName,PTI,PTITrainingDate,MondayPhone\nD1,Alex,DONE,2026-11-09,0012345\nD2,Alex,DONE,,0098765\n'


def test_import_persists_original_and_survives_reload(tmp_path, dvir):
    path = str(tmp_path / 'private' / 'training.sqlite3')
    rows = parse_training(CSV, 'training.csv')
    assert rows[0]['MondayPhone'] == '0012345'
    save_training(path, 'training.csv', CSV, rows)
    saved, timestamp = load_training(path)
    assert timestamp and saved['D1']['training_status'] == 'completed'
    assert saved['D2']['training_completed_at'] is None
    envelope = adapt([dvir])
    merged = merge_training(envelope, saved)
    assert envelope.drivers == []
    data = normalize(merged, 'UTC')
    assert data.drivers.driver_id.tolist() == ['D1']
    assert data.training.iloc[0].training_completed_at == '2026-11-09'
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT original FROM training_imports').fetchone()[0] == CSV
    newer = [{'SamsaraDriverID': 'D1', 'PTI': 'DONE', 'PTITrainingDate': '2026-11-12'}]
    save_training(path, 'new.json', json.dumps(newer).encode(), newer)
    latest, _ = load_training(path)
    assert latest['D1']['training_completed_at'] == '2026-11-12'
    assert 'D2' in latest
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM training_imports').fetchone()[0] == 2


def test_missing_ids_conflicts_and_invalid_dates():
    rows = [
        {'SamsaraDriverID': '', 'PTI': 'DONE'},
        {'SamsaraDriverID': 'D1', 'PTI': 'DONE', 'PTITrainingDate': '2026-11-09'},
        {'SamsaraDriverID': 'D1', 'PTI': 'incomplete'},
        {'SamsaraDriverID': 'D2', 'PTI': 'DONE', 'PTITrainingDate': '11/09/26'},
        {'SamsaraDriverID': 'D3', 'PTI': 'something'},
    ]
    result = summarize_training(rows)
    assert '' not in result
    assert result['D1']['training_status'] == 'unknown'
    assert result['D2'] == {'training_status': 'completed', 'training_completed_at': None}
    assert result['D3']['training_status'] == 'unknown'


@pytest.mark.parametrize('contents', [b'SamsaraDriverID,PTI,PTITrainingDate\n', b'Other\n1\n'])
def test_invalid_file_does_not_save(contents):
    with pytest.raises(ValueError):
        parse_training(contents, 'training.csv')


@pytest.mark.parametrize('suffix,engine', [('xls', 'xlrd'), ('xlsx', 'openpyxl')])
def test_excel_reader_selection(monkeypatch, suffix, engine):
    import pandas as pd
    def read_excel(*args, **kwargs):
        assert kwargs['engine'] == engine
        return pd.DataFrame([{'SamsaraDriverID': 'DEMO-D001', 'PTI': 'DONE', 'PTITrainingDate': '2026-11-09'}])
    monkeypatch.setattr(pd, 'read_excel', read_excel)
    assert parse_training(b'fixture', f'training.{suffix}')[0]['PTI'] == 'DONE'
