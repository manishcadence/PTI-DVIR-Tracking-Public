from src.companions import companion_activity
from src.data_adapter import adapt
from src.filters import reporting_dates
from src.normalization import normalize
from src.source_associations import source_associations, source_shared_vehicles
from datetime import date


def source(driver_id, name, vehicle='V1'):
    return {'driverID': driver_id, 'driverName': name, 'samsaraVehicleid': vehicle,
            'vehicleName': vehicle, 'vehicleIDs': [vehicle], 'trailerIDs': ['T1'],
            'totalPTI': 1, 'vehicleCount': 1, 'trailerCount': 0, 'tripTypes': ['preTrip'],
            'startTimes': ['2026-11-12T12:00:00Z'], 'endTimes': ['2026-11-12T12:10:00Z']}


def test_source_count_zero_and_associations_are_preserved():
    first = source('D1', 'Same name')
    second = source('D1', 'Same name', 'V2')
    second.update(vehicleCount=2, trailerCount=3, totalPTI=5)
    rows = source_associations([first, second, first])
    assert len(rows) == 3
    assert rows.source_row.tolist() == [1, 2, 3]
    assert rows.source_trailer_PTIs.tolist() == [1, 1, 1]
    assert rows.source_vehicle_plus_trailer_PTIs.tolist() == [2, 2, 2]
    assert rows.reported_trailerCount.tolist() == [0, 3, 0]


def test_different_ids_with_same_name_are_distinct_authors():
    shared = source_shared_vehicles([source('D1', 'Same name'), source('D2', 'Same name')])
    assert shared.iloc[0].distinct_DVIR_authors == 2
    assert shared.iloc[0].author_ids == 'D1, D2'


def test_companion_own_dvir_counts_match_name_and_vehicle_not_name_alone():
    first = source('D1', 'Author')
    first.update(cogoID_0='C1', driverName_0='Author', cogoID_1='C2', driverName_1='Partner')
    data = normalize(adapt([first, source('D2', 'Partner'), source('D3', 'Partner', 'V2')]), 'UTC')
    rows = companion_activity(data, reporting_dates(7, date(2026, 11, 16)))
    row = rows.iloc[0]
    assert row.co_driver_id_from_source == 'D2'
    assert row.co_driver_DVIRs_in_selected_window == 1
    assert row.co_driver_pre_post_trips_in_selected_window == 1
    assert row.co_driver_source_trailer_PTIs == 1
    assert row.co_driver_source_vehicle_plus_trailer_PTIs == 2


def test_equipment_entries_not_reported_count_keys_drive_totals():
    row = source('D1', 'Driver')
    row.update(vehicleIDs=['V1', 'V2'], trailerIDs=['T1', 'T2', None, ''],
               vehicleCount=0, trailerCount=0)
    counts = source_associations([row]).iloc[0]
    assert counts.source_vehicle_PTIs == 2
    assert counts.source_trailer_PTIs == 2
    assert counts.source_vehicle_plus_trailer_PTIs == 4


def test_same_name_same_vehicle_ambiguity_is_not_reported_as_zero():
    first = source('D1', 'Author')
    first.update(cogoID_0='C1', driverName_0='Author', cogoID_1='C2', driverName_1='Partner')
    data = normalize(adapt([first, source('D2', 'Partner'), source('D3', 'Partner')]), 'UTC')
    rows = companion_activity(data, reporting_dates(7, date(2026, 11, 16)))
    import pandas as pd
    assert pd.isna(rows.iloc[0].co_driver_DVIRs_in_selected_window)
    assert 'Multiple source IDs' in rows.iloc[0].co_driver_match
