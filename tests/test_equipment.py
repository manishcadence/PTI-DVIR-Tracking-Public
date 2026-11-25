from src.data_adapter import adapt
from src.equipment import equipment_summary
from src.equipment import report_vehicle_names
from src.normalization import normalize


def test_multiple_grouped_assets_stay_visible_without_date_assignment():
    row = {'driverID': 'D1', 'driverName': 'Alex', 'totalPTI': 1,
           'startTimes': ['2026-11-15T12:00:00Z'], 'tripTypes': ['preTrip'],
           'vehicleIDs': ['V1', 'V2'], 'vehicleNames': ['Truck 1', 'Truck 2'],
           'trailerIDs': ['T1', 'T2'], 'trailerNames': ['Trailer 1', 'Trailer 2']}
    records = normalize(adapt([row]), 'UTC').dvir_records
    assert records.vehicle_id.isna().all()
    assert records.trailer_id.isna().all()
    summary = equipment_summary(records).iloc[0]
    assert summary.vehicle_names == 'Truck 1, Truck 2'
    assert summary.vehicle_ids == 'V1, V2'
    assert summary.trailer_names == 'Trailer 1, Trailer 2'
    assert summary.trailer_ids == 'T1, T2'


def test_native_equipment_and_id_only_trailer(dvir):
    dvir['trailer'] = {'id': 'T1'}
    summary = equipment_summary(normalize(adapt([dvir]), 'UTC').dvir_records).iloc[0]
    assert summary.vehicle_names == 'Tractor'
    assert summary.trailer_ids == 'T1'
    assert summary.trailer_names == 'Not supplied'


def test_joined_and_multiple_vehicle_names_are_retained_in_driver_and_record_tables():
    import pandas as pd
    rows = [{'driverID': 'D1', 'driverName': 'Alex', 'totalPTI': 1,
             'vehicleName': 'Joined truck', 'vehicleNames': ['Truck A', 'Truck B'],
             'vehicleIDs': ['V1', 'V2'], 'startTimes': ['2026-11-15T12:00:00Z'],
             'tripTypes': ['preTrip']},
            {'driverID': 'D_ZERO', 'driverName': 'Jordan', 'totalPTI': 0,
             'vehicleName': 'Roster truck', 'vehicleNames': []}]
    records = normalize(adapt(rows), 'UTC').dvir_records
    summary = equipment_summary(records, rows).set_index('driver_id')
    assert summary.loc['D1', 'vehicle_names'] == 'Joined truck, Truck A, Truck B'
    assert summary.loc['D_ZERO', 'vehicle_names'] == 'Roster truck'
    frame = pd.DataFrame({'driver_id': ['D1', 'D_ZERO', 'NO_NAME']}, index=[8, 2, 6])
    enriched = report_vehicle_names(frame, records, rows)
    assert enriched.index.tolist() == [8, 2, 6]
    assert enriched.vehicle_names_in_report.tolist() == [
        'Joined truck, Truck A, Truck B', 'Roster truck', 'Not supplied']
    details = report_vehicle_names(records[['dvir_id', 'vehicle_name']], records, rows)
    assert details.vehicle_name.isna().all()
    assert details.vehicle_names_in_report.iloc[0] == 'Joined truck, Truck A, Truck B'
