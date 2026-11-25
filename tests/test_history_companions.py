from copy import deepcopy
from datetime import date

from src.analytics import driver_activity
from src.companions import listed_companions
from src.data_adapter import adapt
from src.equipment import equipment_summary
from src.filters import apply_filters, reporting_dates, Filters
from src.history import history_summary
from src.normalization import normalize


def source_row():
    return {'driverID': 'D1', 'driverName': 'Author', 'totalPTI': 1,
            'tripTypes': ['preTrip'], 'safetyStatuses': ['safe'],
            'startTimes': ['2026-11-01T12:00:00Z'], 'endTimes': ['2026-11-01T12:10:00Z'],
            'vehicleIDs': ['V1'], 'vehicleNames': ['Truck 1'],
            'trailerIDs': ['T1'], 'cogoID_0': 'C2', 'driverName_0': 'Partner',
            'cogoID_1': 'C1', 'driverName_1': 'Author', 'samsaraVehicleid': 'V1',
            'SamsaraDriverId': 'UNRELATED', 'vehicleName': 'Truck 1'}


def test_full_history_last_pti_survives_empty_board():
    data = normalize(adapt([source_row()]), 'America/Chicago')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 16)), Filters())
    assert driver_activity(scope).iloc[0].submissions == 0
    result = history_summary(data, scope.dates[-1]).iloc[0]
    assert result.last_pti_available_history == date(2026, 11, 1)
    assert result.days_since_last_pti_available_history == 15


def test_join_metadata_does_not_double_count_and_equipment_is_retained():
    row = source_row()
    repeated = deepcopy(row)
    repeated.update(trailerIDs=['T2'], safetyStatuses=['safe', 'safe'], vin='extra')
    data = normalize(adapt([row, repeated, row]), 'UTC')
    assert len(data.dvir_records) == 1
    assert len(data.source_rows) == 3
    assert equipment_summary(data.dvir_records, data.source_rows).iloc[0].trailer_ids == 'T1, T2'
    assert data.dvir_records.iloc[0].author_id == 'D1'


def test_companion_in_slot_zero_is_visible_without_identity_or_credit_guess():
    row = source_row()
    candidates = listed_companions([row, row])
    assert len(candidates) == 1
    assert candidates.iloc[0].cogo_id == 'C2'
    assert candidates.iloc[0].listed_driver_name == 'Partner'
    assert 'unverified' in candidates.iloc[0].relationship
    data = normalize(adapt([row]), 'UTC')
    assert data.team_assignments.empty
    assert data.dvir_records.iloc[0].author_id == 'D1'


def test_unknown_author_slot_keeps_crew_for_review():
    row = source_row()
    row['driverName'] = 'Different person'
    candidates = listed_companions([row])
    assert len(candidates) == 2
    assert candidates.relationship.str.contains('needs review').all()


def test_mixed_pre_post_trips_are_included_in_last_done():
    row = source_row()
    row['tripTypes'] = ['preTrip', 'postTrip']
    data = normalize(adapt([row]), 'UTC')
    result = history_summary(data, date(2026, 11, 16)).iloc[0]
    import pandas as pd
    assert result.last_pti_available_history == date(2026, 11, 1)
    assert result.last_inspection_available_history == date(2026, 11, 1)
    assert pd.isna(result.last_mixed_type_inspection)


def test_history_includes_native_authors_without_a_roster(dvir):
    data = normalize(adapt([dvir]), 'UTC')
    result = history_summary(data, date(2026, 11, 16)).set_index('driver_id')
    assert result.loc['D1', 'last_pti_available_history'] == date(2026, 11, 15)
