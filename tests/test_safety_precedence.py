from datetime import date

import pytest

from src.analytics import daily_status
from src.data_adapter import adapt
from src.filters import Filters, apply_filters, reporting_dates
from src.normalization import normalize


@pytest.mark.parametrize('statuses,selected,mark', [
    (['safe', 'resolved'], 'resolved', 1),
    (['safe', 'resolved', 'unsafe'], 'unsafe', 3),
    (['safe', 'pending'], 'pending', 2),
    (['safe', 'safe'], 'safe', 1),
    ([], 'unknown', 2),
])
def test_safety_values_are_prioritized_and_displayed(statuses, selected, mark):
    source = {'driverID': 'D1', 'totalPTI': 1, 'tripTypes': ['preTrip'],
              'safetyStatuses': statuses, 'startTimes': ['2026-11-15T12:00:00Z']}
    data = normalize(adapt([source]), 'UTC')
    assert data.dvir_records.iloc[0].safety_status == selected
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 16)), Filters())
    assert daily_status(scope, ['D1']).loc['D1', date(2026, 11, 15)] == mark
