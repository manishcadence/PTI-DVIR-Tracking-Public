import pandas as pd
import pytest

from src.data_adapter import PayloadError, adapt
from src.normalization import normalize


def test_optional_fields_and_duplicates(dvir):
    record = normalize(adapt({"data": [dvir, dvir]}), "America/Chicago").dvir_records
    assert len(record) == 1
    row = record.iloc[0]
    assert row.total_defects == row.unresolved_defects == 0
    assert row.raw == dvir
    assert pd.isna(row.trailer_id) and pd.isna(row.officer_name) and pd.isna(row.co_driver_id)


def test_unresolved_and_resolved_defects(dvir):
    dvir["safetyStatus"] = "unsafe"
    dvir["vehicleDefects"] = [
        {"status": "open", "resolvedAtTime": "2026-11-15T10:00:00Z"},
        {"resolution": {"resolvedAtTime": "2026-11-15T11:00:00Z", "mechanicNotes": "Repaired"}},
        {"resolvedAtTime": "unknown"},
    ]
    data = normalize(adapt([dvir]), "UTC")
    row = data.dvir_records.iloc[0]
    assert row.safety_status == "unsafe"
    assert (row.total_defects, row.resolved_defects, row.unresolved_defects) == (3, 1, 2)
    assert data.dvir_defects.mechanic_notes.iloc[1] == "Repaired"


def test_malformed_and_missing_timestamps(dvir):
    dvir["startTime"] = "malformed"
    other = {**dvir, "id": "X2", "endTime": None}
    data = normalize(adapt([dvir, other]), "America/Chicago")
    first, second = data.dvir_records.itertuples(index=False)
    assert pd.isna(first.start_time) and first.ambiguous
    assert str(first.inspection_date) == "2026-11-15"
    assert pd.isna(second.inspection_date)


def test_custom_wrapper(dvir):
    envelope = adapt({"jobs": [dvir], "people": [{"id": "D1"}], "rosterComplete": True},
                     ("jobs", "people", "officers", "pairs"))
    assert envelope.roster_complete


@pytest.mark.parametrize("payload", [None, {}, {"data": [None]}, {"data": [], "pagination": {"hasNextPage": True}}])
def test_invalid_envelopes(payload):
    with pytest.raises(PayloadError):
        adapt(payload)


def test_valid_empty_response():
    data = normalize(adapt({"data": []}), "UTC")
    assert data.dvir_records.empty and data.dvir_defects.empty


def test_version_two_joins_training_and_keeps_assignments(dvir):
    source = {
        "schemaVersion": 2, "rosterComplete": True, "dvirs": [dvir],
        "roster": [{"id": "D1"}, {"id": "D2"}],
        "driverOfficerAssignments": [{"driver_id": "D1", "safety_officer_id": "SO1"}],
        "vehicleOfficerAssignments": [{"vehicle_id": "V2", "safety_officer_id": "SO1"}],
        "trainingRecords": [{"driver_id": "D1", "training_status": "completed",
                             "training_completed_at": "2026-11-09"}],
    }
    data = normalize(adapt(source), "UTC")
    assert data.roster_complete
    assert data.training.training_status.tolist() == ["completed", "unknown"]
    assert data.vehicle_assignments.vehicle_id.tolist() == ["V2"]
    assert data.driver_assignments.set_index("driver_id").loc["D1", "officer_id"] == "SO1"
    source["trainingRecords"].append({"driver_id": "D1", "training_status": "incomplete"})
    assert adapt(source).drivers[0]["training_status"] == "unknown"
    del source["driverOfficerAssignments"]
    with pytest.raises(PayloadError):
        adapt(source)
