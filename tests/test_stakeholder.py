from datetime import date

from src.analytics import driver_activity
from src.data_adapter import adapt
from src.filters import Filters, apply_filters, officer_key, officer_labels, reporting_dates
from src.normalization import normalize
from src.stakeholder import daily_participation, officer_summary, recording_groups
from src.stakeholder import daily_activity_report


def test_missing_officer_keeps_drivers_counts_and_unassigned_filter(dvir):
    source = {'inspections': [dvir], 'drivers': [{'id': 'D1'}, {'id': 'D2'}], 'rosterComplete': True}
    data = normalize(adapt(source), 'UTC')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 16)), Filters())
    drivers = driver_activity(scope)
    assert len(drivers) == 2 and drivers.submissions.sum() == 1
    assert officer_labels(drivers).eq('Unassigned').all()
    assert officer_key(drivers).eq('unknown').all()
    officers = officer_summary(drivers, 7)
    assert officers.iloc[0].drivers == 2
    assert officers.iloc[0].recorded == 1
    unassigned = apply_filters(data, scope.dates, Filters(officer='unknown'))
    assert set(unassigned.drivers.driver_id) == {'D1', 'D2'}
    assert len(unassigned.records) == 1
    trend = daily_participation(scope)
    assert (trend.Recorded + trend['No record']).eq(2).all()
    assert recording_groups(drivers, 7).drivers.sum() == 2


def test_placeholder_names_fall_back_to_real_officer_id(dvir):
    source = {'inspections': [dvir], 'drivers': [
        {'id': 'D1', 'safety_officer_id': 'SO1', 'safety_officer_name': 'Unknown'},
        {'id': 'D2', 'safety_officer_name': 'Unassigned'},
    ], 'rosterComplete': True}
    scope = apply_filters(normalize(adapt(source), 'UTC'), reporting_dates(7, date(2026, 11, 16)), Filters())
    labels = officer_labels(scope.drivers).tolist()
    assert labels == ['SO1', 'Unassigned']
    assert officer_key(scope.drivers).tolist() == ['id:SO1', 'unknown']


def test_daily_graph_separates_people_from_records_and_keeps_zero_days(dvir):
    from copy import deepcopy
    second = deepcopy(dvir)
    second.update(id='X2', type='postTrip')
    source = {'inspections': [dvir, second], 'drivers': [{'id': 'D1'}, {'id': 'D2'}],
              'rosterComplete': True}
    data = normalize(adapt(source), 'UTC')
    dates = reporting_dates(7, date(2026, 11, 16))
    scope = apply_filters(data, dates, Filters())
    daily = daily_activity_report(scope).set_index('date')
    assert len(daily) == 7
    active = daily.loc[date(2026, 11, 15)]
    assert active.drivers_with_PTI == 1 and active.PTI_records == 2
    assert active.drivers_without_record == 1 and active.share_of_drivers_percent == 50
    assert daily.loc[date(2026, 11, 16), 'drivers_with_PTI'] == 0
    assert daily.loc[date(2026, 11, 16), 'PTI_records'] == 0
    empty = apply_filters(data, dates, Filters(driver='missing-driver'))
    assert daily_activity_report(empty).share_of_drivers_percent.eq(0).all()
