from datetime import date

import pytest

from src.analytics import calculate_expected_ptis, daily_status, driver_activity, pretrips
from src.data_adapter import adapt
from src.filters import Filters, apply_filters, reporting_dates
from src.normalization import normalize


@pytest.mark.parametrize("days,earlier_included", [(7, False), (15, True)])
def test_period_and_distinct_days(dvir, days, earlier_included):
    earlier = {**dvir, "id": "X3", "startTime": "2026-11-04T06:00:00Z", "endTime": None}
    data = normalize(adapt({
        "inspections": [dvir, {**dvir, "id": "X2", "safetyStatus": "unsafe"}, earlier,
                        {**dvir, "id": "X4", "type": "postTrip"}],
        "drivers": [{"id": "D1"}, {"id": "D2"}], "rosterComplete": True,
    }), "America/Chicago")
    scope = apply_filters(data, reporting_dates(days, date(2026, 11, 15)), Filters())
    summary = driver_activity(scope).set_index("driver_id")
    assert summary.loc["D1", "submissions"] == 3 + earlier_included
    assert summary.loc["D1", "recorded_days"] == 1 + earlier_included
    assert summary.loc["D1", "days_without_pti"] == days - 1 - earlier_included
    assert summary.loc["D2", "activity"] == "No recorded PTI"
    assert daily_status(scope, ["D1", "D2"]).iloc[:, -1].tolist() == [3, 0]
    assert len(scope.records) == len(pretrips(scope.records)) + 1
    assert calculate_expected_ptis("D1") is None


def test_local_date_and_combined_filters(dvir):
    dvir.update(startTime="2026-11-15T02:00:00Z", co_driver_id="D2",
                trailer={"id": "T2"}, safety_officer_id="old")
    data = normalize(adapt({"inspections": [dvir], "drivers": [{"id": "D1", "safety_officer_id": "new"}]}),
                     "America/Chicago")
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 15)),
                          Filters("id:new", "alex", "V1", "T2", "D2"))
    assert scope.records.inspection_date.tolist() == [date(2026, 11, 14)]
    assert scope.records.officer_id.tolist() == ["new"]


def test_empty_scope():
    scope = apply_filters(normalize(adapt([]), "UTC"), reporting_dates(7, date.today()), Filters())
    assert driver_activity(scope).empty


def test_fleet_scale(dvir):
    drivers = [{"id": f"D{i}", "name": f"Driver {i}"} for i in range(800)]
    records = [
        {**dvir, "id": f"{driver['id']}-{day}",
         "authorSignature": {"signatoryUser": driver},
         "startTime": f"2026-11-{day:02d}T06:00:00Z",
         "endTime": f"2026-11-{day:02d}T06:10:00Z"}
        for driver in drivers for day in range(1, 16)
    ]
    data = normalize(adapt({"inspections": records, "drivers": drivers, "rosterComplete": True}), "UTC")
    scope = apply_filters(data, reporting_dates(15, date(2026, 11, 15)), Filters())
    activity = driver_activity(scope)
    assert len(activity) == 800
    assert activity.submissions.sum() == 12_000
    assert daily_status(scope, activity.driver_id.head(20).tolist()).shape == (20, 15)


def test_training_date_only_skips_same_day_pti(dvir):
    from datetime import datetime, timezone

    from src.followup import training_followup

    data = normalize(adapt({
        "rosterComplete": True,
        "drivers": [{"id": "D1", "training_status": "completed",
                     "training_completed_at": "2026-11-15"}],
        "inspections": [dvir],
        "vehicleAssignments": [{"vehicle_id": "V2", "safety_officer_id": "SO2"}],
    }), "UTC")
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 16)), Filters())
    view = training_followup(driver_activity(scope), data.training, scope, "UTC",
                             datetime(2026, 11, 16, 12, tzinfo=timezone.utc))
    assert view.training_follow_up.tolist() == ["Trained · No PTI recorded since training"]
    assert data.vehicle_assignments.vehicle_id.tolist() == ["V2"]
