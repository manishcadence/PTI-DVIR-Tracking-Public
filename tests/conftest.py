"""Shared synthetic records."""
import pytest


@pytest.fixture(autouse=True)
def isolate_local_report_configuration(monkeypatch, tmp_path):
    """Tests opt in to grouped input instead of inheriting the user's .env."""
    monkeypatch.setenv('PTI_LOCAL_JSON_PATH', '')
    monkeypatch.setenv('PTI_UPLOAD_ONLY', 'false')
    monkeypatch.setenv('PTI_HISTORY_DB', str(tmp_path / 'history.sqlite3'))
    monkeypatch.setenv('PTI_HISTORY_BACKUP_DIR', str(tmp_path / 'backups'))


@pytest.fixture
def dvir():
    return {
        "id": "X1", "type": "preTrip", "startTime": "2026-11-15T06:00:00Z",
        "endTime": "2026-11-15T06:10:00Z", "safetyStatus": "safe",
        "authorSignature": {"signatoryUser": {"id": "D1", "name": "Alex"}},
        "vehicle": {"id": "V1", "name": "Tractor"}, "vehicleDefects": [], "trailerDefects": [],
    }
