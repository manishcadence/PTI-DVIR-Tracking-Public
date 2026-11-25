from datetime import date, datetime, timezone

from src.analytics import daily_status, driver_activity
from src.data_adapter import adapt
from src.filters import apply_filters, reporting_dates, Filters
from src.followup import training_followup
from src.normalization import normalize


def test_mixed_pre_post_trips_count_as_done_and_green_with_known_safety():
    grouped = {'driverID': 'D1', 'totalPTI': 2, 'tripTypes': ['preTrip', 'postTrip'],
               'safetyStatuses': ['safe'],
               'startTimes': ['2026-11-15T12:00:00Z', '2026-11-16T12:00:00Z']}
    data = normalize(adapt([grouped]), 'America/Chicago')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 17)), Filters())
    activity = driver_activity(scope)
    row = activity.iloc[0]
    assert row.activity == 'Intermittent submitter'
    assert row.submissions == 2 and row.inspection_type_review == 0
    marks = daily_status(scope, ['D1'])
    assert marks.loc['D1', date(2026, 11, 15)] == 1
    assert marks.loc['D1', date(2026, 11, 16)] == 1
    assert marks.loc['D1', date(2026, 11, 17)] == 0
    data.training.loc[:, 'training_status'] = 'completed'
    data.training.loc[:, 'training_completed_at'] = '2026-11-14'
    followup = training_followup(activity, data.training, scope, 'America/Chicago',
                                now=datetime(2026, 11, 17, 20, tzinfo=timezone.utc))
    assert followup.iloc[0].training_follow_up == 'Trained · PTI recorded since training'


def test_review_does_not_override_confirmed_or_unsafe(dvir):
    grouped = {'driverID': 'D1', 'totalPTI': 1, 'tripTypes': ['preTrip', 'postTrip'],
               'startTimes': ['2026-11-15T12:00:00Z']}
    envelope = adapt([grouped])
    dvir['safetyStatus'] = 'unsafe'
    envelope.inspections.append(dvir)
    data = normalize(envelope, 'UTC')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 17)), Filters())
    row = driver_activity(scope).iloc[0]
    assert row.submissions == 2 and row.inspection_type_review == 0
    assert row.activity == 'Intermittent submitter'
    assert daily_status(scope, ['D1']).loc['D1', date(2026, 11, 15)] == 3


def test_post_trip_only_counts_as_done_and_missing_dates_remain_insufficient(dvir):
    dvir['type'] = 'postTrip'
    data = normalize(adapt([dvir]), 'UTC')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 17)), Filters())
    assert driver_activity(scope).iloc[0].submissions == 1
    assert daily_status(scope, ['D1']).loc['D1', date(2026, 11, 15)] == 1
    dvir.update(startTime=None, endTime=None)
    data = normalize(adapt({'inspections': [dvir], 'drivers': [{'id': 'D1'}], 'rosterComplete': True}), 'UTC')
    scope = apply_filters(data, scope.dates, Filters())
    assert driver_activity(scope).iloc[0].activity == 'Insufficient information'
