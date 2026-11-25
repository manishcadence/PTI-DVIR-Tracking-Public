from copy import deepcopy
from datetime import date

import pytest

from src.data_adapter import adapt
from src.equipment import equipment_summary
from src.filters import Filters, apply_filters, reporting_dates, source_assets_match
from src.normalization import normalize
from src.ui import Context


def source():
    return {'driverID': 'D1', 'driverName': 'Alex', 'totalPTI': 1,
            'tripTypes': ['preTrip'], 'startTimes': ['2026-11-15T12:00:00Z'],
            'vehicleIDs': ['V1', 'V2'], 'vehicleNames': ['Truck A', 'Truck B'],
            'trailerIDs': ['T1', 'T2'], 'trailerNames': ['Trailer A', 'Trailer B']}


@pytest.mark.parametrize('filters', [Filters(vehicle='V2'), Filters(vehicle='truck b'),
                                    Filters(trailer='T2'), Filters(trailer='trailer b'),
                                    Filters(vehicle='V2', trailer='T2')])
def test_filters_search_all_grouped_asset_values(filters):
    data = normalize(adapt([source()]), 'UTC')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 16)), filters)
    assert len(scope.records) == 1
    assert scope.drivers.driver_id.tolist() == ['D1']


def test_alternate_source_trailer_survives_timestamp_deduplication():
    original = source()
    alternate = deepcopy(original)
    alternate.update(vehicleIDs=['V3'], vehicleNames=['Truck C'], trailerIDs=['T3'], trailerNames=['Trailer C'])
    data = normalize(adapt([original, alternate]), 'UTC')
    assert len(data.dvir_records) == 1
    filters = Filters(vehicle='V3', trailer='T3')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 16)), filters)
    assert len(scope.records) == 1
    context = Context(data=data, scope=scope, timezone='UTC', filters=filters)
    assert len(context.filtered_source_rows) == 1
    assert context.filtered_source_rows[0]['_source_row_number'] == 2
    equipment = equipment_summary(scope.records, context.filtered_source_rows).iloc[0]
    assert equipment.vehicle_ids == 'V3' and equipment.trailer_ids == 'T3'
    # Asset conditions must match the same source association.
    incompatible = apply_filters(data, scope.dates, Filters(vehicle='V1', trailer='T3'))
    assert incompatible.records.empty


def test_missing_and_literal_assets_do_not_match():
    assert not source_assets_match(source(), Filters(vehicle='V9'))
    assert not source_assets_match(source(), Filters(vehicle='.*'))
    assert not source_assets_match(source(), Filters(trailer='[T1]'))
