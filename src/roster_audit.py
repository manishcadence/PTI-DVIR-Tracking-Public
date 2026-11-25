"""Actionable checks over joined source rows; expected join repetition is not fraud."""
from collections import defaultdict
import json
import re
import pandas as pd
from .roster import holiday_dates, roster_metadata
from .data_adapter import identifier


def roster_audit(data):
    findings = []
    def add(level, check, number, driver, detail):
        findings.append({'severity': level, 'check': check, 'source_row': number,
                         'driver_id': driver, 'detail': detail})
    crosswalk = {key: defaultdict(set) for key in ('Tms_ID', 'COGOELD')}
    histories = defaultdict(list)
    for number, source in enumerate(data.source_rows, 1):
        driver = source.get('_roster_driver_id')
        if not driver:
            continue
        sid = identifier(source.get('Samsara_DriverID'))
        if source.get('_missing_author_detail'):
            add('Review','Inspection author ID missing',number,driver,'Reported counts/timestamps are retained, but the author cannot be identified. Export the original inspection author ID.')
        if source.get('_multi_author_aggregate'):
            add('Review','Multiple authors in one aggregate',number,driver,
                'Source counts and dates may describe a team. Per-inspection author IDs are needed for individual credit.')
        if source.get('_inspection_alignment_review'):
            add('Error','Appended timestamp arrays are not aligned',number,driver,
                'Start/end arrays differ in length. Reported totals are retained; individual dated events are not invented.')
        license_a = re.sub('[^A-Z0-9]', '', str(source.get('Tms_licenseNumber') or '').upper())
        license_b = re.sub('[^A-Z0-9]', '', str(source.get('Samsara_licenseNumber') or '').upper())
        if license_a and license_b and license_a != license_b:
            add('Review', 'TMS and Samsara license values differ', number, driver,
                'License values differ after removing formatting. Verify the identity crosswalk or stale source details; do not change identity automatically.')
        if not sid:
            add('Review', 'Missing Samsara ID', number, driver, 'Roster retained using TMS ID; no name-only DVIR credit.')
        for key in crosswalk:
            value = identifier(source.get(key))
            if value and sid:
                crosswalk[key][value].add(sid)
        holidays = holiday_dates(source.get('appended_status_date'))
        reported = source.get('count_status_date')
        if reported is not None and str(reported).strip() and str(reported) != str(len(holidays)):
            add('Review', 'Holiday count differs from dates', number, driver,
                f'Reported count {reported}; distinct supplied holiday dates {len(holidays)}. Use dates for calendar calculations.')
        author = source.get('_dvir_author_id')
        if author and sid and author != sid:
            cogo = identifier(source.get('COGOELD'))
            slots = [identifier(source.get(f'cogoID_{i}')) for i in range(3)]
            if cogo and cogo in slots:
                add('Information', 'Separate co-driver author', number, driver,
                    f'Roster Cogo ID matches crew; DVIR author {author} keeps their own inspection credit.')
            else:
                add('Review', 'Unverified author-to-roster join', number, driver,
                    f'DVIR author {author} differs and no roster Cogo ID matches crew.')
        starts, ends = source.get('startTimes') or [], source.get('endTimes') or []
        if starts and ends and len(starts) != len(ends):
            add('Error', 'Unaligned start/end arrays', number, driver, 'Start and end arrays have different lengths.')
        if (starts or ends) and source.get('totalPTI') != max(len(starts), len(ends)):
            add('Review', 'Count differs from timestamp pairs', number, driver, 'Use dated pairs for dated activity; reported count differs.')
        for key, values in [('startTimes', starts), ('endTimes', ends)]:
            invalid = [value for value in values if value is not None and pd.isna(pd.to_datetime(value, utc=True, errors='coerce'))]
            if invalid:
                add('Error', 'Invalid inspection timestamps', number, driver, f'{key}: {len(invalid)} values cannot be parsed.')
        for start, end in zip(starts, ends):
            a, b = pd.to_datetime(start, utc=True, errors='coerce'), pd.to_datetime(end, utc=True, errors='coerce')
            if pd.notna(a) and pd.notna(b) and b < a:
                add('Error', 'Inspection ends before it starts', number, driver, 'Check source timestamp alignment; keep this record for review.')
        if starts or ends:
            signature = json.dumps([author, starts, ends], sort_keys=True)
            histories[signature].append((number, driver))
        if source.get('uniqueVehicleCount', 0) and source.get('uniqueVehicleCount', 0) > len(set(source.get('vehicleIDs') or [])):
            add('Review', 'Vehicle inventory information lost', number, driver,
                'Reported uniqueVehicleCount exceeds supplied distinct vehicle IDs. Export all vehicleIDs and vehicleNames.')
    name_matches = sum('name' in str(row.get('MatchReason') or '').lower() for row in data.source_rows)
    if name_matches:
        add('Review', 'Name-based roster identity crosswalk', None, None,
            f'{name_matches} source rows report a name-based TMS-to-Samsara match. Maintain a verified TMS_ID-to-Samsara_DriverID crosswalk; a name match alone does not establish identity.')
    from .workforce import status_label
    status_values=defaultdict(set)
    for source in data.source_rows:
        subject=source.get('_status_subject_id')
        value=status_label(source.get('_source_status'))
        if subject and value!='Unknown':
            status_values[subject].add(value)
    for subject,values in status_values.items():
        if len(values)>1:
            add('Review','Conflicting Samsara account statuses',None,subject,
                'Active and deactivated values are supplied for this same account. Status stays Unknown until the source is reconciled.')
    for key, mapping in crosswalk.items():
        for value, matches in mapping.items():
            if len(matches) > 1:
                add('Error', 'Ambiguous ID crosswalk', None, None, f'{key} {value} maps to multiple Samsara IDs: {sorted(matches)}')
    for group in histories.values():
        if len(group) > 1:
            add('Information', 'Repeated joined inspection history', group[0][0], group[0][1],
                f'Same author and timestamp arrays on {len(group)} rows; count dated history once, retain source associations.')
    metadata = roster_metadata(data)
    for row in data.dvir_records.itertuples(index=False):
        if row.author_id in metadata and row.inspection_date in metadata[row.author_id]['holidays']:
            add('Review', 'Inspection on a holiday date', None, row.author_id,
                f'{row.inspection_date}: could be a return, partial day or outdated holiday record; keep the actual inspection.')
    if any('_roster_driver_id' in row for row in data.source_rows):
        add('Information', 'Original DVIR IDs unavailable', None, None,
            'Source id is a roster/database row ID, not a Samsara DVIR ID. Export original inspection IDs for exact history matching.')
    return pd.DataFrame(findings, columns=['severity','check','source_row','driver_id','detail']).drop_duplicates()
