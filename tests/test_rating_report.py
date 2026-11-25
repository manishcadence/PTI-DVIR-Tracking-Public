from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pandas as pd

from src.data_adapter import adapt
from src.filters import reporting_dates
from src.normalization import normalize
from src.rating_guide import data_dictionary, rating_guide_html
from src.rating_report import build_rating_report, daily_rating_evidence, report_bundle
from src.source_associations import source_associations


def test_export_includes_zero_activity_and_older_drivers_with_missing_inputs_blank(dvir):
    old = {**dvir, 'id': 'OLD', 'startTime': '2026-11-01T12:00:00Z',
           'endTime': '2026-11-01T12:10:00Z',
           'authorSignature': {'signatoryUser': {'id': 'D2', 'name': 'Old record'}}}
    payload = {'inspections': [dvir, old], 'drivers': [{'id': 'D1', 'name': 'Alex'},
               {'id': 'D3', 'name': 'No activity'}], 'rosterComplete': False}
    data = normalize(adapt(payload), 'UTC')
    dates = reporting_dates(7, date(2026, 11, 16))
    report = build_rating_report(data, dates, 'UTC').set_index('driver_id')
    assert set(report.index) == {'D1', 'D2', 'D3'}
    assert report.loc['D1', 'dated_pre_post_trip_records_window'] == 1
    assert report.loc['D2', 'dated_pre_post_trip_records_window'] == 0
    assert report.loc['D2', 'last_done_date_available_history'] == date(2026, 11, 1)
    assert report.loc['D3', 'calendar_dates_without_record_window'] == 7
    assert report.loc['D3', 'training_status'] == 'unknown'
    assert report.safety_score.isna().all()
    assert report.verified_missed_required_inspections_window.isna().all()
    assert report.driving_miles_window.isna().all()
    assert report.loc['D1', 'reported_defects_window'] == 0
    assert pd.isna(report.loc['D3', 'reported_defects_window'])
    assert len(daily_rating_evidence(data, dates)) == 3 * 7


def test_grouped_safety_flags_are_not_exported_as_verified_event_counts():
    row = {'driverID': 'D1', 'driverName': 'Alex', 'totalPTI': 1,
           'tripTypes': ['preTrip', 'postTrip'], 'startTimes': ['2026-11-15T12:00:00Z'],
           'vehicleIDs': ['V1'], 'trailerIDs': ['T1', 'T2'], 'vehicleCount': 0,
           'trailerCount': 0, 'safetyStatuses': ['safe', 'unsafe']}
    other = {**row, 'trailerIDs': ['T3']}
    data = normalize(adapt([row, other]), 'UTC')
    report = build_rating_report(data, reporting_dates(7, date(2026, 11, 16)), 'UTC')
    result = report.iloc[0]
    assert result.dated_pre_post_trip_records_window == 1
    assert result.equipment_combined_list_entries_full_source == 5
    assert result.unsafe_equipment_status_flag_in_source
    assert pd.isna(result.verified_unsafe_inspection_count_window)
    assert pd.isna(result.reported_defects_window)
    assert result.defect_detail_coverage_window == 'not_supplied'
    assert len(data_dictionary(report)) == len(report.columns)
    bundle = report_bundle(report, daily_rating_evidence(data, reporting_dates(7, date(2026, 11, 16))),
                           source_associations(data.source_rows), data_dictionary(report), rating_guide_html())
    with ZipFile(BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {'driver_rating_inputs.csv', 'daily_inspection_evidence.csv',
                                        'source_vehicle_crew_rows.csv', 'data_dictionary.csv', 'rating_guide.html'}


def test_rating_export_handles_empty_feed():
    data = normalize(adapt([]), 'UTC')
    report = build_rating_report(data, reporting_dates(7, date(2026, 11, 16)), 'UTC')
    assert report.empty and 'driver_id' in report.columns and 'safety_score' in report.columns
