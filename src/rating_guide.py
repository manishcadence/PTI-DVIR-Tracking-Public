"""Field definitions and research references shipped with the rating-input export."""
from html import escape

import pandas as pd

from .rating_report import MISSING_INPUTS


DEFINITIONS = {
    'driver_id': 'Stable Samsara DVIR author ID; one summary row per ID. Same names with different IDs remain separate.',
    'driver_name': 'Driver display name; not an identity-join key.',
    'report_start_date': 'First inclusive local calendar date of the selected 7/15-day report.',
    'report_end_date': 'Last inclusive activity-window date, based on the latest actual inspection in local JSON. Export metadata is tracked separately and does not move the window onto an empty date.',
    'window_calendar_days': 'Selected calendar-day denominator; not days driven or required inspections.',
    'dated_pre_post_trip_records_window': 'Unique authored timestamp/DVIR records in the window, accepting preTrip and postTrip. Equipment-list totals are separate.',
    'days_with_recorded_inspection_window': 'Distinct local dates with an accepted authored inspection; multiple same-day submissions count as one date.',
    'calendar_dates_without_record_window': 'Window days minus recorded dates. Not verified required-inspection misses.',
    'recorded_calendar_day_percent': '100 × recorded dates / calendar days. Activity coverage only; not a compliance or safety score.',
    'is_regular_recorder': 'Meets the user-defined 4/7 or 8/15 recorded-date threshold; not a validated risk classification.',
    'regular_minimum_recorded_days': '4 for seven days, 8 for fifteen days.',
    'recording_frequency': 'Frequent, intermittent, no recorded PTI, or insufficient information using dated activity evidence.',
    'training_status': 'Verified-ID matched completed/incomplete/not_trained/unknown. Missing records stay unknown.',
    'training_completed_at': 'Verified training completion date or timestamp. A date-only cutoff begins on the following local date.',
    'training_follow_up_as_of_report_end': 'Recorded activity after the training cutoff inside this window, assessed through the report end, not the computer date.',
    'last_done_date_window': 'Most recent authored accepted pre/post-trip date within this window.',
    'days_since_last_done_within_window': 'Report end minus last done within this window; blank when no match.',
    'last_done_date_available_history': 'Latest accepted authored inspection date across all supplied history through report end.',
    'days_since_last_done_available_history': 'Report end minus last done in supplied history, including inspections older than the selected window.',
    'last_inspection_date_available_history': 'Latest dated authored inspection of any type through report end.',
    'earliest_inspection_date_supplied_for_driver': 'Earliest dated record for the author; does not establish complete coverage between endpoints.',
    'history_coverage_verified': 'False: the payload does not attest complete source-level history coverage.',
    'roster_complete_verified': 'Explicit rosterComplete signal from source; not assumed from a list of observed authors.',
    'current_safety_officer_id': 'Current assigned safety officer ID, when supplied; not historical responsibility.',
    'current_safety_officer_name': 'Current assigned safety officer display name.',
    'vehicle_ids': 'Distinct supplied vehicle IDs across available source history.',
    'vehicle_names': 'Supplied vehicle names; not guaranteed aligned with each asset ID or date.',
    'trailer_ids': 'Distinct supplied trailer IDs across available source history.',
    'trailer_names': 'Supplied trailer names when provided.',
    'source_row_count': 'Count of original source rows for this driver; differing equipment/crew rows remain present.',
    'equipment_vehicle_list_entries_full_source': 'Count each nonempty vehicleIDs entry across every source row for this author. Full history, not this date window.',
    'equipment_trailer_list_entries_full_source': 'Count each nonempty trailerIDs entry across every source row for this author. Empty arrays contribute zero.',
    'equipment_combined_list_entries_full_source': 'Vehicle-list entries + trailer-list entries, preserving every source association row. Do not add to timestamp records.',
    'source_safety_statuses_available_history': 'All supplied safety statuses for this author. Grouped summaries do not locate each status on a specific date.',
    'unsafe_equipment_status_flag_in_source': 'Unsafe equipment status was supplied; review context. Not evidence of unsafe driving or driver fault.',
    'resolved_equipment_status_flag_in_source': 'A resolved status was supplied; not verified mechanic repair evidence without defect-level records.',
    'safety_status_scope': 'Distinguishes grouped driver-summary status from inspection-level status.',
    'verified_unsafe_inspection_count_window': 'Inspection-level unsafe statuses only. Blank for grouped summaries whose status-to-date assignment is unknown.',
    'defect_detail_coverage_window': 'complete/partial/not_supplied/no_inspections_in_window for explicit vehicleDefects and trailerDefects arrays.',
    'reported_defects_window': 'Count of detailed defect rows only when defect-array coverage is complete. Reporting a defect is not driver fault.',
    'unresolved_reported_defects_window': 'Detailed unresolved defects only with complete array coverage; a maintenance follow-up item, not an automatic driver penalty.',
    'cogo_listed_companions_unverified': 'Source-listed vehicle crew names/Cogo IDs; no historical pairing time or automatic identity verification.',
    'confirmed_team_inspections_window': 'Explicit confirmed team involvement for the author. Blank when grouped export cannot establish inspection-time teams.',
    'undated_record_count_available_history': 'Authored records excluded from dated counts because neither start nor end is usable.',
    'timestamp_review_record_count_window': 'Accepted records with missing start or end-before-start. Does not assume a required inspection duration.',
    'inspection_type_review': 'Window records mixing accepted pre/post-trip with unsupported types. Pre/post mixtures alone do not need review.',
    'data_quality_notes': 'Provenance limitations and count/coverage review flags; do not automatically convert them to driver penalties.',
    'rating_input_status': 'Available inputs are partial; broader verified outcomes and driving exposure are not supplied.',
    'safety_score': 'Intentionally blank. No unsupported weights or individual safety score have been assigned.',
    'missing_data_policy': 'Blank means unavailable, not zero, no violations, or poor performance.',
    'export_scope': 'All supplied drivers and observed authors; sidebar, daily-card and pagination filters are ignored.',
    'inspection_count_basis': 'Author-only dated record count, distinct from equipment-list entry totals.',
    'equipment_count_basis': 'User-specified full-source list-entry counting rule; no asset-to-date multiplication.',
    'source_format': 'Grouped driver export or individual inspection records.',
    'generated_at_utc': 'UTC generation timestamp of this export.',
    'report_schema_version': 'Version of this CSV field contract.',
    'reporting_timezone': 'Timezone used to convert RFC 3339 instants to calendar dates.',
    'rating_note': 'Interpretation rules to preserve in downstream rating software.',
}


def data_dictionary(report):
    rows = []
    for column in report.columns:
        missing = column in MISSING_INPUTS
        definition = DEFINITIONS.get(column)
        if not definition and missing:
            definition = ('Not supplied by the current inspection/training feed. Add verified ' +
                          column.replace('_window', '').replace('_', ' ') +
                          ' from an appropriate source before use; window fields must match the report period.')
        rows.append({'column': column, 'definition': definition or column.replace('_', ' '),
                     'availability': 'blank_pending_external_source_or_manager_review' if missing else 'derived_or_supplied',
                     'missing_value_rule': 'blank = unavailable; retain explicit observed zeros'})
    return pd.DataFrame(rows)


SOURCES = [
    ('FMCSA: Safety Measurement System categories and evidence', 'https://csa.fmcsa.dot.gov/about/measure'),
    ('FMCSA: SMS does not assign formal ratings to individual drivers', 'https://csa.fmcsa.dot.gov/HelpCenter/GetFAQsPage'),
    ('FMCSA Safety Planner: DVIR reporting and carrier corrective action', 'https://csa.fmcsa.dot.gov/safetyplanner/MyFiles/SubSections.aspx?ch=22&sec=65&sub=148'),
    ('NIOSH: fleet KPIs, mileage exposure, training and driving-performance evidence', 'https://archive.cdc.gov/www_cdc_gov/niosh/motorvehicle/ncmvs/newsletter/ncmvsnewsletterv6n2.html'),
    ('OSHA: training-schedule adherence as a leading indicator', 'https://www.osha.gov/motor-vehicle-safety/employers'),
]


def rating_guide_html():
    links = ''.join(f'<li><a href="{escape(url)}">{escape(title)}</a></li>' for title, url in SOURCES)
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Driver rating input guide</title>
<style>body{{font:16px/1.6 system-ui;max-width:960px;margin:40px auto;padding:0 24px;color:#172940}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border:1px solid #dce3eb;text-align:left}}th{{background:#f0f4f9}}</style>
<h1>Driver safety rating: input guide</h1><p>Research reviewed November 17, 2026. This export supplies evidence for review; it does not assign a safety score.</p>
<h2>Use these dimensions separately</h2><table><tr><th>Dimension</th><th>Available now</th><th>Additional evidence needed</th></tr>
<tr><td>Inspection recording and follow-through</td><td>Authored pre/post-trip dates, frequency, recency, training follow-up</td><td>Driving starts, eligible days, company inspection policy, complete multi-platform records</td></tr>
<tr><td>Training and coaching</td><td>Verified-ID training status/date where uploaded</td><td>Verified coaching completion and subsequent behavior</td></tr>
<tr><td>Driving behavior</td><td>Not supplied</td><td>Verified speeding, seatbelt, distraction and HOS events with miles/hours and reviewed driver attribution</td></tr>
<tr><td>Crashes and roadside violations</td><td>Not supplied</td><td>Reviewed preventability, driver-attributable violations, severity, exposure and sufficient observation history</td></tr>
<tr><td>Equipment reporting and corrective action</td><td>Equipment lists and grouped statuses; detailed defects only when supplied</td><td>Defect-level resolution, repair verification and responsibility context</td></tr></table>
<h2>Interpretation rules</h2><ul><li>Regular means the user-defined 4 of 7 or 8 of 15 calendar dates. It is not a validated driver-risk classification.</li>
<li>Calendar dates without a record are not verified missed required inspections. No eligible-driving denominator is available.</li>
<li>Equipment-list entry counts cover the full supplied source. They are separate from dated timestamp records and are not multiplied across dates.</li>
<li>Blank means unavailable, not zero. Zero is retained only for an observable count with adequate evidence.</li>
<li>Do not penalize a driver for reporting an unsafe vehicle or defect. Reporting a condition does not establish fault; repair/corrective action requires separate evidence.</li>
<li>Grouped status flags are not inspection-level event counts. A Resolved label does not itself prove a verified repair.</li>
<li>Use stable driver IDs; same names remain separate. Cogo-listed crew does not transfer authored inspection credit.</li>
<li>FMCSA SMS prioritizes motor carriers and does not assign formal individual-driver safety ratings. This export is not an FMCSA rating.</li>
<li>Before adding a score, establish auditable definitions, verified responsibility, suitable exposure denominators, an adequate observation period, and a manager review/correction process. No arbitrary score or weighting has been filled in here.</li></ul>
<h2>Files</h2><p>driver_rating_inputs.csv: one row per driver. daily_inspection_evidence.csv: one driver/date per row. source_vehicle_crew_rows.csv: every original source association, including multiple vehicles/crews. data_dictionary.csv: definitions for every summary field.</p>
<h2>Primary sources</h2><ul>{links}</ul></html>'''
