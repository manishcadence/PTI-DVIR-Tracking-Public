import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.analytics import daily_status, driver_activity
from src.data_adapter import PayloadError, adapt
from src.filters import Filters, apply_filters, reporting_dates
from src.normalization import normalize


@pytest.fixture
def grouped():
    path = Path(__file__).resolve().parent / "fixtures" / "grouped_example.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("days,total", [(7, 5), (15, 7)])
def test_grouped_example_reporting(grouped, days, total):
    envelope = adapt(grouped)
    data = normalize(envelope, "America/Chicago")
    scope = apply_filters(data, reporting_dates(days, date(2026, 11, 17)),
                          Filters(officer="name:Demo Officer"))
    summary = driver_activity(scope).iloc[0]
    assert summary.driver_id == "DEMO-D001"
    assert summary.submissions == summary.recorded_days == total
    assert summary.vehicles == 1
    assert summary.last_pti == date(2026, 11, 16)
    assert daily_status(scope, [summary.driver_id]).iloc[0].sum() == total
    assert envelope.notices and not envelope.roster_complete
    assert data.training.training_status.isna().all()
    assert data.vehicle_assignments.empty and data.team_assignments.empty
    assert data.dvir_signatures.empty


def test_grouped_wrappers_and_stable_ids(grouped):
    row = grouped["driverSummaries"][0]
    expected = adapt(grouped).inspections
    for payload in (row, [row], {"data": [row]}, {"inspections": [row]}):
        assert adapt(payload).inspections == expected
    # Repeated identical summary rows must not double count inspections.
    assert len(normalize(adapt([row, row]), "UTC").dvir_records) == 7


def test_grouped_does_not_invent_per_inspection_mapping(grouped):
    row = grouped["driverSummaries"][0]
    row.update(vehicleIDs=["V1", "V2"], vehicleNames=["One", "Two"],
               safetyStatuses=["safe", "unsafe"], safetyOfficers=["Alice", "Bob"])
    data = normalize(adapt(grouped), "UTC")
    assert data.dvir_records.vehicle_id.isna().all()
    assert data.dvir_records.officer_name.isna().all()
    assert data.dvir_records.safety_status.eq("unsafe").all()
    assert not data.dvir_records.ambiguous.any()


@pytest.mark.parametrize("change", [
    {"endTimes": ["2026-11-09T10:01:03.327Z"]}, {"startTimes": [] , "endTimes": []},
    {"startTimes": "0:2026-11-09T09:59:22.701Z"}, {"totalPTI": "7"},
    {"driverID": None},
])
def test_grouped_rejects_lost_alignment(grouped, change):
    grouped["driverSummaries"][0].update(change)
    with pytest.raises(PayloadError):
        adapt(grouped)


def test_grouped_missing_times_and_local_date(grouped):
    row = grouped["driverSummaries"][0]
    row["startTimes"][0] = None
    row["endTimes"][1] = None
    row["startTimes"][2] = "2026-11-11T02:00:00Z"
    records = normalize(adapt(grouped), "America/Chicago").dvir_records
    assert records.iloc[0].ambiguous
    assert records.iloc[2].inspection_date == date(2026, 11, 10)
    assert pd.isna(records.iloc[1].end_time)


def test_grouped_zero_activity_roster(grouped):
    row = deepcopy(grouped["driverSummaries"][0])
    row.update(totalPTI=0, startTimes=[], endTimes=[])
    data = normalize(adapt({"rosterComplete": True, "driverSummaries": [row]}), "UTC")
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 17)), Filters())
    assert driver_activity(scope).iloc[0].submissions == 0


def test_grouped_count_mismatch_uses_available_timestamps(grouped):
    grouped["driverSummaries"][0]["totalPTI"] = 14
    envelope = adapt(grouped)
    assert len(envelope.inspections) == 7
    assert any("count mismatch" in notice for notice in envelope.notices)


@pytest.mark.parametrize('days,observed', [(7, 1), (15, 2)])
def test_supplied_population_does_not_shrink_with_period(grouped, days, observed):
    current = grouped['driverSummaries'][0]
    older = deepcopy(current)
    older.update(driverID='D_OLD', driverName='Older record', totalPTI=1,
                 startTimes=['2026-11-09T12:00:00Z'], endTimes=['2026-11-09T12:10:00Z'])
    zero = deepcopy(current)
    zero.update(driverID='D_ZERO', totalPTI=0, startTimes=[], endTimes=[])
    data = normalize(adapt([current, older, zero]), 'America/Chicago')
    assert not data.roster_complete
    scope = apply_filters(data, reporting_dates(days, date(2026, 11, 17)), Filters())
    summary = driver_activity(scope).set_index('driver_id')
    assert len(summary) == 3
    assert scope.records.author_id.nunique() == observed
    assert summary.loc['D_ZERO', 'submissions'] == 0
    assert summary.loc['D_OLD', 'submissions'] == (1 if days == 15 else 0)
    filtered = apply_filters(data, scope.dates, Filters(driver='D_OLD'))
    assert filtered.drivers.driver_id.tolist() == ['D_OLD']
