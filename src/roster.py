"""Date-aware roster availability and source-linked crew, independent of authorship."""
from datetime import date, timedelta
import re
import pandas as pd
from .analytics import recorded_inspections
from .data_adapter import identifier


def has_roster(data):
    return any('_roster_driver_id' in row for row in data.source_rows)


def holiday_dates(value):
    values = value if isinstance(value, list) else re.findall(r'\d{4}-\d{2}-\d{2}', str(value or ''))
    output = set()
    for value in values:
        try:
            output.add(date.fromisoformat(str(value)[:10]))
        except ValueError:
            pass
    return output


def roster_metadata(data):
    groups = {}
    for source in data.source_rows:
        key = source.get('_roster_driver_id')
        if not key:
            continue
        entry = groups.setdefault(key, {'driver_id': key, 'driver_name': source.get('Samsara_DriverName') or source.get('Tms_driverName') or 'Unknown',
                                        'tms_id': source.get('Tms_ID'), 'cogo_id': source.get('COGOELD'),
                                        'id_match_basis': source.get('MatchReason') or 'Not supplied',
                                        'holidays': set(), 'vehicle_names': set(), 'trailer_ids': set(),
                                        'training': set(), 'needs_samsara_id': not bool(source.get('Samsara_DriverID')),
                                        'identity_review': not bool(source.get('Samsara_DriverID')),
                                        'in_roster':False,'date_attribution_review':False})
        license_a = re.sub('[^A-Z0-9]', '', str(source.get('Tms_licenseNumber') or '').upper())
        license_b = re.sub('[^A-Z0-9]', '', str(source.get('Samsara_licenseNumber') or '').upper())
        entry['identity_review'] |= bool(license_a and license_b and license_a != license_b)
        entry['in_roster'] |= source.get('_is_roster_member',True)
        entry['date_attribution_review'] |= bool(source.get('_multi_author_aggregate') or source.get('_inspection_alignment_review') or source.get('_missing_author_detail'))
        entry['holidays'].update(holiday_dates(source.get('appended_status_date')))
        entry['vehicle_names'].update(str(x).strip() for x in source.get('vehicleNames', []) if str(x).strip())
        if source.get('vehicleName'):
            entry['vehicle_names'].add(str(source['vehicleName']))
        entry['trailer_ids'].update(str(x) for x in source.get('trailerIDs', []) if x)
        if source.get('PTITraining'):
            entry['training'].add(str(source['PTITraining']))
    from .workforce import account_statuses, source_crews
    statuses=account_statuses(data)
    crews=source_crews(data)
    team_members={member for crew in crews.values() for member in crew['members']}
    uncertain_members={member for crew in crews.values() if any(row.get('_multi_author_aggregate') or row.get('_missing_author_detail') or row.get('_inspection_alignment_review') for row in crew['sources']) for member in crew['members']}
    for entry in groups.values():
        entry['samsara_status']=statuses.get(entry['driver_id'],'Unknown')
        entry['driver_mode']='Co-driver' if entry['driver_id'] in team_members else 'Solo'
        entry['date_attribution_review'] |= entry['driver_id'] in uncertain_members
        for key in ('vehicle_names', 'trailer_ids', 'training'):
            entry[key] = ', '.join(sorted(entry[key])) or 'Not supplied'
    return groups


def roster_summary(data, dates, selected_day):
    metadata = roster_metadata(data)
    from .workforce import distinct_activity
    accepted = distinct_activity(data)
    history = accepted[accepted.inspection_time.notna() & accepted.inspection_date.le(selected_day)]
    period = history[history.inspection_date.isin(dates)]
    rows = []
    for key, entry in metadata.items():
        own = history[history.author_id.eq(key)]
        window = period[period.author_id.eq(key)]
        recorded_days = set(window.inspection_date)
        last = own.inspection_date.max() if len(own) else None
        age = (selected_day - last).days if last is not None else None
        holidays = entry['holidays']
        is_holiday = selected_day in holidays
        previous = [d for d in holidays if d < selected_day]
        return_date = max(previous) + timedelta(days=1) if previous and not is_holiday else None
        availability = 'On holiday' if is_holiday else 'Available'
        regular = len(recorded_days) >= (len(dates) + 1) // 2
        rows.append({**{k:v for k,v in entry.items() if k != 'holidays'},
                     'availability': availability, 'PTI_records': len(window), 'recorded_dates': len(recorded_days),
                     'consistency': 'Regular' if regular else 'Intermittent' if recorded_days else 'Needs individual DVIR detail' if entry['date_attribution_review'] else 'No matched DVIR',
                     'PTI_on_selected_date': bool(len(own[own.inspection_date.eq(selected_day)])),
                     'last_done': last, 'days_since_last_PTI': age,
                     'recent_activity': 'PTI in last 0–2 days' if age is not None and age <= 2 else
                         'PTI 3–6 days ago' if age is not None and age <= 6 else 'PTI 7+ days ago' if age is not None else 'No matched DVIR',
                     'holiday_dates_in_window': len(set(dates) & holidays),
                     'nonholiday_dates_without_PTI': len(set(dates) - holidays - recorded_days),
                     'available_since_last_holiday': return_date,
                     'returned_recently': return_date is not None and 0 <= (selected_day - return_date).days <= 2})
    return pd.DataFrame(rows)


def roster_daily(data, dates, driver_ids=None):
    metadata = roster_metadata(data)
    ids = set(driver_ids) if driver_ids is not None else set(metadata)
    accepted = recorded_inspections(data.dvir_records)
    output = []
    for day in dates:
        holiday = {key for key in ids if day in metadata[key]['holidays']}
        done = set(accepted.loc[accepted.inspection_date.eq(day), 'author_id']) & ids
        output.append({'date': day, 'available': len(ids - holiday), 'on_holiday': len(holiday),
                       'drivers_with_own_PTI': len(done),
                       'available_without_own_PTI': len(ids - holiday - done)})
    return pd.DataFrame(output)


def roster_links(data, dates):
    metadata = roster_metadata(data)
    crosswalk = {}
    for key, entry in metadata.items():
        cogo = identifier(entry['cogo_id'])
        if cogo:
            crosswalk.setdefault(cogo, set()).add(key)
    accepted = recorded_inspections(data.dvir_records)
    period = accepted[accepted.inspection_date.isin(dates)]
    counts = period.groupby('author_id').size()
    last = accepted[accepted.inspection_date.le(dates[-1])].groupby('author_id').inspection_date.max()
    links = []
    for source in data.source_rows:
        owner = source.get('_roster_driver_id')
        if not owner:
            continue
        cogo = identifier(source.get('COGOELD'))
        author = source.get('_dvir_author_id')
        slots = [(identifier(source.get(f'cogoID_{i}')), source.get(f'driverName_{i}')) for i in range(3)]
        matches = [cid for cid, _ in slots if cogo and cid == cogo]
        partners = []
        if author and author != owner and matches:
            partners.append((author, source.get('driverName') or author, 'Roster Cogo ID matches source crew; separate DVIR author'))
        else:
            for cid, name in slots:
                if not cid or cid == cogo:
                    continue
                candidates = crosswalk.get(cid, set())
                partner = next(iter(candidates)) if len(candidates) == 1 else None
                partners.append((partner, name or cid, 'Source Cogo ID crosswalk' if partner else 'Listed crew; Samsara ID not verified'))
        for partner, name, basis in partners:
            links.append({'driver_id': owner, 'driver_name': metadata[owner]['driver_name'],
                          'vehicle_names_in_report': source.get('vehicleName') or metadata[owner]['vehicle_names'],
                          'partner_id': partner, 'partner_name': name, 'association': basis,
                          'driver_own_PTIs': int(counts.get(owner, 0)),
                          'partner_own_PTIs': int(counts.get(partner, 0)) if partner else None,
                          'partner_last_done': last.get(partner),
                          'credit': 'Each inspection belongs only to its DVIR author'})
    return pd.DataFrame(links).drop_duplicates() if links else pd.DataFrame(columns=['driver_id','driver_name','partner_id','partner_name'])
