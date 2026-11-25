"""Evidence-based, all-driver inputs for a downstream safety review system."""
from datetime import datetime, timedelta, timezone as utc_timezone
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from .analytics import daily_status, driver_activity, recorded_inspections
from .companions import companion_summary
from .components.tables import csv_bytes
from .equipment import equipment_summary
from .filters import Filters, Scope, apply_filters
from .followup import training_followup
from .history import history_summary
from .source_associations import source_associations


MISSING_INPUTS = [
    'eligible_driving_days_window', 'expected_required_inspections_window',
    'verified_missed_required_inspections_window', 'inspection_compliance_percent',
    'driving_miles_window', 'driving_hours_window', 'preventable_crashes_window',
    'roadside_inspections_window', 'driver_attributable_violations_window',
    'driver_out_of_service_violations_window', 'hos_violations_window',
    'verified_speeding_events_window', 'seatbelt_events_window',
    'distracted_driving_events_window', 'coaching_completion_status',
    'manager_review_outcome', 'safety_score',
]

DETAIL_COLUMNS = [
    'source_format', 'source_row_count', 'equipment_vehicle_list_entries_full_source',
    'equipment_trailer_list_entries_full_source', 'equipment_combined_list_entries_full_source',
    'equipment_count_basis', 'source_safety_statuses_available_history',
    'unsafe_equipment_status_flag_in_source', 'resolved_equipment_status_flag_in_source',
    'safety_status_scope', 'verified_unsafe_inspection_count_window', 'defect_detail_coverage_window',
    'reported_defects_window', 'unresolved_reported_defects_window', 'confirmed_team_inspections_window',
    'earliest_inspection_date_supplied_for_driver', 'undated_record_count_available_history',
    'timestamp_review_record_count_window', 'data_quality_notes', 'rating_input_status',
]


def all_driver_scope(data, dates):
    """Export supplied roster plus observed authors, independent of all UI filters."""
    scope = apply_filters(data, dates, Filters())
    # Include explicitly supplied drivers and authors anywhere in available history.
    from .filters import driver_population
    from dataclasses import replace
    scope.drivers = driver_population(replace(data, retain_supplied_drivers=True), data.dvir_records)
    extra=data.dvir_records[~data.dvir_records.author_id.isin(scope.drivers.driver_id)].dropna(subset=['author_id']).drop_duplicates('author_id',keep='last')
    if not extra.empty:
        observed=extra[['author_id','author_name','officer_id','officer_name']].rename(columns={'author_id':'driver_id','author_name':'driver_name'})
        scope.drivers=pd.concat([scope.drivers,observed],ignore_index=True)
    scope.records=data.dvir_records[data.dvir_records.inspection_date.isin(dates)]

    return scope


def build_rating_report(data, dates, timezone):
    scope = all_driver_scope(data, dates)
    report = driver_activity(scope)
    as_of = pd.Timestamp(dates[-1] + timedelta(days=1), tz=timezone).to_pydatetime()
    report = training_followup(report, data.training, scope, timezone, now=as_of)
    report.training_status = report.training_status.fillna('unknown')
    report = report.merge(history_summary(data, dates[-1]), on='driver_id', how='left')
    report = report.merge(equipment_summary(data.dvir_records, data.source_rows or None), on='driver_id', how='left')
    report = report.merge(companion_summary(data.source_rows), on='driver_id', how='left')
    report.cogo_listed_companions = report.cogo_listed_companions.fillna('')
    from .roster import has_roster, roster_metadata
    if has_roster(data):
        from .workforce import account_statuses
        metadata=roster_metadata(data)
        statuses=account_statuses(data)
        report['samsara_status']=report.driver_id.map(statuses).astype('string').fillna('Unknown')
        report['roster_match']=report.driver_id.map(lambda key:'Matched roster' if metadata.get(key,{}).get('in_roster') else 'Needs review')
        report['driver_mode']=report.driver_id.map(lambda key:metadata.get(key,{}).get('driver_mode','Not verified'))
    report = report.rename(columns={
        'officer_id': 'current_safety_officer_id', 'officer_name': 'current_safety_officer_name',
        'submissions': 'dated_pre_post_trip_records_window', 'recorded_days': 'days_with_recorded_inspection_window',
        'days_without_pti': 'calendar_dates_without_record_window',
        'last_pti': 'last_done_date_window', 'days_since_last_pti': 'days_since_last_done_within_window',
        'activity': 'recording_frequency', 'last_pti_available_history': 'last_done_date_available_history',
        'days_since_last_pti_available_history': 'days_since_last_done_available_history',
        'last_inspection_available_history': 'last_inspection_date_available_history',
        'training_follow_up': 'training_follow_up_as_of_report_end',
        'cogo_listed_companions': 'cogo_listed_companions_unverified',
    })
    # Remove normalized counters whose grouped-source scope could look like verified safety events.
    report = report.drop(columns=['vehicles', 'unsafe', 'unresolved', 'co_driver', 'last_mixed_type_inspection'], errors='ignore')
    report.insert(0, 'report_schema_version', '1.0')
    report['generated_at_utc'] = datetime.now(utc_timezone.utc).isoformat()
    report['report_start_date'] = dates[0]
    report['report_end_date'] = dates[-1]
    report['reporting_timezone'] = timezone
    report['window_calendar_days'] = len(dates)
    report['regular_minimum_recorded_days'] = (len(dates) + 1) // 2
    report['is_regular_recorder'] = report.days_with_recorded_inspection_window.ge((len(dates) + 1) // 2)
    report['recorded_calendar_day_percent'] = (100 * report.days_with_recorded_inspection_window / len(dates)).round(2)
    report['inspection_count_basis'] = 'unique authored timestamp records; preTrip and postTrip; not equipment-list totals'
    report['roster_complete_verified'] = data.roster_complete
    report['history_coverage_verified'] = False
    report['export_scope'] = 'all supplied drivers and observed authors; UI filters ignored'

    source_by_driver = {}
    for row in data.source_rows:
        source_by_driver.setdefault(str(row.get('driverID')), []).append(row)
    records_by_driver = {key: group for key, group in data.dvir_records.groupby('author_id')}
    dated_by_driver = {key: group for key, group in recorded_inspections(scope.records).groupby('author_id')}
    extra = []
    for driver_id in report.driver_id:
        sources = source_by_driver.get(driver_id, [])
        history = records_by_driver.get(driver_id, data.dvir_records.iloc[:0])
        window = dated_by_driver.get(driver_id, data.dvir_records.iloc[:0])
        grouped = bool(sources) or any(isinstance(raw, dict) and raw.get('sourceFormat') == 'groupedDriver' for raw in history.raw)
        statuses = {str(value).strip().lower() for row in sources for value in row.get('safetyStatuses', [])
                    if isinstance(value, str) and value.strip()}
        if not grouped:
            statuses.update(history.safety_status.dropna())
        arrays = source_associations(sources)
        defect_known = window.raw.map(lambda raw: isinstance(raw, dict) and
                                      isinstance(raw.get('vehicleDefects'), list) and
                                      isinstance(raw.get('trailerDefects'), list)).astype(bool)
        coverage = ('no_inspections_in_window' if window.empty else 'complete' if defect_known.all()
                    else 'partial' if defect_known.any() else 'not_supplied')
        defects = data.dvir_defects[data.dvir_defects.dvir_id.isin(window.dvir_id)]
        starts = history[history.inspection_time.notna()]
        quality = []
        if grouped:
            quality.append('grouped_source_without_original_DVIR_IDs_or_asset_date_mapping')
        if len(sources) > 1:
            quality.append('multiple_source_associations_retained')
        undated = int(history.inspection_time.isna().sum())
        if undated:
            quality.append('undated_records')
        if any(row.get('totalPTI') != max(len(row.get('startTimes') or []), len(row.get('endTimes') or [])) for row in sources):
            quality.append('reported_count_differs_from_timestamp_count')
        extra.append({
            'source_format': 'grouped_driver_export' if grouped else 'individual_inspections',
            'source_row_count': len(sources),
            'equipment_vehicle_list_entries_full_source': int(arrays.source_vehicle_PTIs.sum()) if sources else pd.NA,
            'equipment_trailer_list_entries_full_source': int(arrays.source_trailer_PTIs.sum()) if sources else pd.NA,
            'equipment_combined_list_entries_full_source': int(arrays.source_vehicle_plus_trailer_PTIs.sum()) if sources else pd.NA,
            'equipment_count_basis': 'nonempty list entries across every supplied source row; full history' if grouped else 'not supplied as grouped lists',
            'source_safety_statuses_available_history': '; '.join(sorted(statuses)),
            'unsafe_equipment_status_flag_in_source': 'unsafe' in statuses if statuses - {'unknown'} else pd.NA,
            'resolved_equipment_status_flag_in_source': 'resolved' in statuses if statuses - {'unknown'} else pd.NA,
            'safety_status_scope': 'driver_summary_not_per_inspection' if grouped else 'individual_inspection',
            'verified_unsafe_inspection_count_window': pd.NA if grouped else int(window.safety_status.eq('unsafe').sum()),
            'defect_detail_coverage_window': coverage,
            'reported_defects_window': int(len(defects)) if coverage == 'complete' else pd.NA,
            'unresolved_reported_defects_window': int(defects.resolution_status.eq('Unresolved').sum()) if coverage == 'complete' else pd.NA,
            'confirmed_team_inspections_window': pd.NA if grouped else int(window.team_confirmed.sum()),
            'earliest_inspection_date_supplied_for_driver': starts.inspection_date.min() if len(starts) else None,
            'undated_record_count_available_history': undated,
            'timestamp_review_record_count_window': int((window.start_time.isna() | (window.end_time < window.start_time)).sum()),
            'data_quality_notes': '; '.join(quality),
            'rating_input_status': 'partial_inputs_missing_driving_exposure_and_verified_safety_outcomes',
        })
    for column in DETAIL_COLUMNS:
        report[column] = [row[column] for row in extra]
    for column in MISSING_INPUTS:
        report[column] = pd.NA
    report['rating_note'] = 'Inputs only; no safety score assigned. Calendar gaps are not verified misses; reporting defects is not driver fault.'
    report['missing_data_policy'] = 'blank means unavailable; do not convert to zero or a penalty'
    report['training_status'] = report.training_status.fillna('unknown')
    first = ['report_schema_version', 'driver_id', 'driver_name', 'current_safety_officer_id', 'current_safety_officer_name',
             'report_start_date', 'report_end_date', 'reporting_timezone', 'window_calendar_days',
             'dated_pre_post_trip_records_window', 'days_with_recorded_inspection_window',
             'calendar_dates_without_record_window', 'recorded_calendar_day_percent', 'is_regular_recorder',
             'regular_minimum_recorded_days', 'recording_frequency', 'last_done_date_window',
             'last_done_date_available_history', 'days_since_last_done_available_history',
             'training_status', 'training_completed_at', 'training_follow_up_as_of_report_end']
    return report[first + [column for column in report.columns if column not in first]].sort_values(['driver_name', 'driver_id'], na_position='last')


def daily_rating_evidence(data, dates):
    scope = all_driver_scope(data, dates)
    marks = daily_status(scope, scope.drivers.driver_id.tolist())
    rows = marks.rename_axis(index='driver_id', columns='inspection_date').stack().rename('mark').reset_index()
    names = scope.drivers[['driver_id', 'driver_name']]
    rows = rows.merge(names, on='driver_id', how='left')
    equipment = equipment_summary(data.dvir_records, data.source_rows or None)
    rows = rows.merge(equipment[['driver_id', 'vehicle_names']], on='driver_id', how='left')
    rows['vehicle_names'] = rows.vehicle_names.fillna('Not supplied')
    counts = recorded_inspections(scope.records).groupby(['author_id', 'inspection_date']).dvir_id.nunique()
    rows['dated_inspection_records'] = [int(counts.get((row.driver_id, row.inspection_date), 0)) for row in rows.itertuples()]
    rows['daily_mark'] = rows.pop('mark').map({0: 'no_record', 1: 'done', 2: 'review', 3: 'unsafe'})
    grouped_authors = {str(source.get('driverID')) for source in data.source_rows}
    rows['status_attribution'] = rows.driver_id.map(
        lambda key: 'grouped_source_status_applied_to_date_not_verified_event' if key in grouped_authors
        else 'inspection_record')
    return rows


def report_bundle(report, daily, associations, dictionary, guide):
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, frame in [('driver_rating_inputs.csv', report), ('daily_inspection_evidence.csv', daily),
                            ('source_vehicle_crew_rows.csv', associations), ('data_dictionary.csv', dictionary)]:
            archive.writestr(name, b'\xef\xbb\xbf' + csv_bytes(frame))
        archive.writestr('rating_guide.html', guide)
    return output.getvalue()
