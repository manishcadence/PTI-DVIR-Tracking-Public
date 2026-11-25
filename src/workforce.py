"""Samsara account status, exact source crews, and separately reviewed DVIR authors."""
from collections import defaultdict
import hashlib
import json
import pandas as pd
from .analytics import recorded_inspections
from .data_adapter import identifier


def status_label(value):
    value = str(value or '').strip().casefold()
    if value in ('active','activated','enabled'):
        return 'Active'
    if value in ('deactive','deactivated','inactive','disabled','archived','deleted'):
        return 'Deactivated'
    return 'Unknown'


def account_statuses(data):
    collected = defaultdict(set)
    for row in data.source_rows:
        subject = row.get('_status_subject_id') or row.get('samsara_driverId') or row.get('Samsara_DriverID')
        value = status_label(row.get('_source_status',row.get('SamsaraStatus')))
        if subject and value != 'Unknown':
            collected[str(subject)].add(value)
    return {key:next(iter(values)) if len(values)==1 else 'Unknown' for key,values in collected.items()}


def source_crews(data):
    """Exact crew-ID sets, never connected components across changing partners."""
    crosswalk = defaultdict(set)
    for row in data.source_rows:
        cid = identifier(row.get('COGOELD'))
        owner = row.get('_roster_driver_id')
        if cid and owner:
            crosswalk[cid].add(owner)
    groups = {}
    for index,row in enumerate(data.source_rows):
        owner, author = row.get('_roster_driver_id'), row.get('_dvir_author_id')
        own_cogo = identifier(row.get('COGOELD'))
        author_name = str(row.get('driverName') or '').strip().casefold()
        slots = [(identifier(row.get(f'cogoID_{i}')),str(row.get(f'driverName_{i}') or '').strip()) for i in range(3)]
        slots = list(dict.fromkeys((cid,name) for cid,name in slots if cid or name))
        cids = sorted({cid for cid,_ in slots if cid})
        own_only = len(slots)==1 and ((own_cogo and slots[0][0]==own_cogo) or
                                      (author_name and slots[0][1].casefold()==author_name))
        if not slots or own_only:
            continue
        if len(cids)>=2:
            identity = ['cogo',*cids]
        elif len(slots)>=2:
            identity = ['unverified-source-crew',index]
        else:
            identity = ['author-and-listed-partner',author or owner,*cids]
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:14]
        group = groups.setdefault(key,{'crew_id':key,'members':set(),'names':set(),'cogo_ids':set(),
                                      'vehicles':set(),'sources':[],'unverified_members':False})
        for cid,name in slots:
            if cid:
                group['cogo_ids'].add(cid)
                matches = crosswalk.get(cid,set())
                if len(matches)==1:
                    group['members'].update(matches)
                else:
                    group['unverified_members']=True
            if not cid:
                group['unverified_members']=True
            if name:
                group['names'].add(name)
        if author:
            group['members'].add(author)
        group['members'].update(row.get('_source_author_ids',[]))
        if owner and own_cogo and own_cogo in cids:
            group['members'].add(owner)
        group['vehicles'].update(str(x) for x in row.get('vehicleNames',[]) if x)
        if row.get('vehicleName'):
            group['vehicles'].add(str(row['vehicleName']))
        group['sources'].append(row)
    return groups


def distinct_activity(data):
    """Stable authored timestamp-pair fallback for overlapping grouped histories."""
    records = recorded_inspections(data.dvir_records)
    seen, keep, occurrences = set(), [], defaultdict(int)
    for index,row in records.iterrows():
        raw = row.raw if isinstance(row.raw,dict) else {}
        if raw.get('sourceFormat')!='groupedDriver':
            key=('dvir',row.dvir_id)
        else:
            source=raw.get('groupedSource',{})
            history=json.dumps([source.get('startTimes'),source.get('endTimes')])
            pair=(row.author_id,str(row.start_time),str(row.end_time))
            occurrences[(history,pair)]+=1
            key=(*pair,occurrences[(history,pair)])
            if pd.isna(row.start_time) and pd.isna(row.end_time):
                key=('undated',row.dvir_id)
        if key not in seen:
            seen.add(key)
            keep.append(index)
    return records.loc[keep]


def source_totals(rows):
    """Deduplicate joined histories; inconsistent counts cannot be safely added."""
    fields=[('_reported_vehicle_count','source_vehicle_count_full_file'),
            ('_reported_trailer_count','source_trailer_count_full_file'),
            ('_reported_totalPTI','source_totalPTI_full_file')]
    grouped=defaultdict(list)
    for row in rows:
        actor=row.get('_dvir_author_id') or row.get('_source_author_ids') or row.get('_roster_driver_id')
        if row.get('_multi_author_aggregate'):
            crew=sorted({str(row.get(f'cogoID_{i}')) for i in range(3) if row.get(f'cogoID_{i}')})
            actor=['aggregate',crew or sorted(row.get('_source_author_ids',[])) or [row.get('_roster_driver_id')]]
        times=[]
        for field in ('startTimes','endTimes'):
            raw=row.get(field) or []
            parsed=pd.to_datetime(pd.Series(raw,dtype='object'),utc=True,errors='coerce',format='mixed')
            times.append([stamp.isoformat() if pd.notna(stamp) else str(original) for stamp,original in zip(parsed,raw)])
        grouped[json.dumps([actor,*times],sort_keys=True)].append(row)
    counts=[]
    conflict=False
    for copies in grouped.values():
        resolved={}
        for source,target in fields:
            supplied={r.get(source) for r in copies if r.get(source) is not None}
            conflict |= len(supplied)>1
            resolved[target]=next(iter(supplied)) if len(supplied)==1 else None
        counts.append(resolved)
    mixed=any(r.get('_multi_author_aggregate') or r.get('_missing_author_detail') for r in rows) and any(
        not r.get('_multi_author_aggregate') and not r.get('_missing_author_detail') and r.get('_dvir_author_id') for r in rows)
    output={}
    for _,target in fields:
        supplied=[group[target] for group in counts]
        output[target]=None if mixed or conflict or not supplied or any(x is None for x in supplied) else sum(supplied)
    output['source_combined_equipment_count_full_file']=(output['source_vehicle_count_full_file']+output['source_trailer_count_full_file']) if output['source_vehicle_count_full_file'] is not None and output['source_trailer_count_full_file'] is not None else None
    output['source_count_note']=('Conflicting counts for the same author/history; review' if conflict else
        'Mixed aggregate/individual totals need review; not summed' if mixed else
        'Reported source counts; repeated identical author histories counted once')
    return output


def team_summary(data,dates,timezone='America/Chicago'):
    groups=source_crews(data)
    statuses=account_statuses(data)
    records=distinct_activity(data)
    period=records[records.inspection_date.isin(dates)]
    rows=[]
    memberships=defaultdict(int)
    for group in groups.values():
        for member in group['members']:
            memberships[member]+=1
    for key,group in groups.items():
        members=sorted(group['members'])
        own=period[period.author_id.isin(members)]
        states={statuses.get(member,'Unknown') for member in members}
        if len(members) < max(len(group['cogo_ids']),len(group['names'])):
            states.add('Unknown')
        team_status=next(iter(states)) if len(states)==1 else 'Mixed' if states else 'Unknown'
        source_dates=set()
        for source in group['sources']:
            if not source.get('_multi_author_aggregate') or source.get('_inspection_alignment_review'):
                continue
            size=max(len(source.get('startTimes') or []),len(source.get('endTimes') or []))
            times=pd.to_datetime(pd.Series(source.get('startTimes') or [],dtype='object').reindex(range(size)),utc=True,errors='coerce',format='mixed')
            ends=pd.to_datetime(pd.Series(source.get('endTimes') or [],dtype='object').reindex(range(size)),utc=True,errors='coerce',format='mixed')
            times=times.fillna(ends)
            source_dates.update(times.dropna().dt.tz_convert(timezone).dt.date)
        dates_done=set(own.inspection_date) | (source_dates & set(dates))
        aggregate=any(row.get('_multi_author_aggregate') or row.get('_inspection_alignment_review') or row.get('_missing_author_detail') for row in group['sources'])
        duration=(own.end_time-own.start_time).dt.total_seconds()/60
        first_time,last_time=own.inspection_time.min(),own.inspection_time.max()
        count_value=None if aggregate else len(own)
        count_basis='Mixed or unattributed source detail; count unavailable' if aggregate else 'Distinct authored records'
        aggregate_histories={}
        for source in group['sources']:
            if not (source.get('_multi_author_aggregate') or source.get('_missing_author_detail')) or source.get('_inspection_alignment_review'):
                continue
            size=max(len(source.get('startTimes') or []),len(source.get('endTimes') or []))
            starts=pd.to_datetime(pd.Series(source.get('startTimes') or [],dtype='object').reindex(range(size)),utc=True,errors='coerce',format='mixed')
            ends=pd.to_datetime(pd.Series(source.get('endTimes') or [],dtype='object').reindex(range(size)),utc=True,errors='coerce',format='mixed')
            signature=tuple(zip(starts.astype(str),ends.astype(str)))
            aggregate_histories[signature]=(starts,ends)
        if aggregate and own.empty and len(aggregate_histories)==1:
            starts,ends=next(iter(aggregate_histories.values()))
            times=starts.fillna(ends)
            selected=times.dt.tz_convert(timezone).dt.date.isin(dates)
            count_value=int(selected.sum())
            count_basis='Unattributed team timestamp pairs; no individual allocation'
            duration=(ends[selected]-starts[selected]).dt.total_seconds()/60
            first_time,last_time=times[selected].min(),times[selected].max()
        valid=duration.notna() & duration.ge(0)
        rows.append({'crew_id':key,'team_members':'; '.join(sorted(group['names'])) or ', '.join(members),
                     'member_ids':', '.join(members), 'vehicle_names':', '.join(sorted(group['vehicles'])) or 'Not supplied',
                     'samsara_status':team_status,'member_statuses':'; '.join(f'{member}: {statuses.get(member,"Unknown")}' for member in members),
                     'has_active_member':'Active' in states,'has_deactivated_member':'Deactivated' in states,'has_unknown_member':'Unknown' in states,
                     'combined_dated_PTIs':count_value,'dated_count_basis':count_basis, 'combined_recorded_dates':len(dates_done),
                     'team_consistency':'Regular' if len(dates_done)>=(len(dates)+1)//2 else 'Intermittent' if dates_done else 'Needs individual DVIR detail' if aggregate else 'No recorded dates',
                     'each_driver_own_PTIs':'; '.join(f'{member}: {int(own.author_id.eq(member).sum())} matched records' + ('; aggregate credit unavailable' if aggregate else '') for member in members),
                     'each_driver_consistency':'; '.join(member + ': ' + ('Regular' if own[own.author_id.eq(member)].inspection_date.nunique()>=(len(dates)+1)//2 else 'Intermittent' if own.author_id.eq(member).any() else 'Needs individual records' if aggregate else 'No matched DVIR') for member in members),
                     'first_PTI_in_window':first_time, 'last_PTI_in_window':last_time,
                     'known_duration_minutes':round(float(duration[valid].sum()),1) if valid.any() else None,
                     'duration_records':int(valid.sum()), 'needs_member_mapping':group['unverified_members'],
                     'multi_author_aggregate':any(r.get('_multi_author_aggregate') for r in group['sources']), 'needs_individual_DVIR_detail':aggregate, 'member_in_multiple_crews':any(memberships[x]>1 for x in members),
                     **source_totals(group['sources'])})
    return pd.DataFrame(rows,columns=['crew_id','team_members','member_ids','vehicle_names','samsara_status','member_statuses',
        'has_active_member','has_deactivated_member','has_unknown_member','combined_dated_PTIs','combined_recorded_dates','dated_count_basis',
        'team_consistency','each_driver_own_PTIs','each_driver_consistency','first_PTI_in_window','last_PTI_in_window','known_duration_minutes','duration_records',
        'needs_member_mapping','multi_author_aggregate','needs_individual_DVIR_detail','member_in_multiple_crews','source_vehicle_count_full_file',
        'source_trailer_count_full_file','source_totalPTI_full_file','source_combined_equipment_count_full_file','source_count_note'])


def review_drivers(data,dates):
    roster_ids={r.get('_roster_driver_id') for r in data.source_rows if r.get('_is_roster_member',True)}
    candidates={r.get('_dvir_author_id') or r.get('_roster_driver_id') for r in data.source_rows if not r.get('_is_roster_member',True)}
    candidates |= set(data.dvir_records.author_id.dropna())-roster_ids
    candidates |= {value for row in data.source_rows for value in row.get('_source_author_ids',[])}-roster_ids
    candidates -= roster_ids
    statuses=account_statuses(data)
    records=distinct_activity(data)
    rows=[]
    crews=source_crews(data)
    for driver in sorted(candidates-{None}):
        sources=[r for r in data.source_rows if r.get('_dvir_author_id')==driver or r.get('_roster_driver_id')==driver or driver in r.get('_source_author_ids',[])]
        history=records[records.author_id.eq(driver)]
        own=history[history.inspection_date.isin(dates)]
        names=[r.get('driverName') for r in sources if r.get('_dvir_author_id')==driver and isinstance(r.get('driverName'),str)]
        names += [r.get('Samsara_DriverName') for r in sources if r.get('_roster_driver_id')==driver]
        vehicles=sorted({str(v) for r in sources for v in r.get('vehicleNames',[]) if v})
        counts=source_totals(sources)
        if any(r.get('_multi_author_aggregate') or r.get('_missing_author_detail') for r in sources):
            for field in ('source_vehicle_count_full_file','source_trailer_count_full_file','source_totalPTI_full_file','source_combined_equipment_count_full_file'):
                counts[field]=None
            counts['source_count_note']='Multi-author or missing-author aggregate: not attributable to this individual'
        linked_crews=[key for key,group in crews.items() if driver in group['members']]
        rows.append({'driver_id':driver,'driver_mode':'Co-driver' if linked_crews else 'Solo','review_crew_ids':', '.join(linked_crews), 'driver_name':next((x for x in names if x),'Unknown'),
                     'vehicle_names':', '.join(vehicles) or 'Not supplied','samsara_status':statuses.get(driver,'Unknown'),
                     'review_tag':'Needs review — not matched to TruckMate/Monday roster',
                     'own_dated_PTIs':len(own),'recorded_dates':own.inspection_date.nunique(),
                     'last_done':history.inspection_time.max(),**counts})
    return pd.DataFrame(rows,columns=['driver_id','driver_name','vehicle_names','driver_mode','review_crew_ids','samsara_status','review_tag','own_dated_PTIs',
        'recorded_dates','last_done','source_vehicle_count_full_file','source_trailer_count_full_file','source_totalPTI_full_file','source_combined_equipment_count_full_file','source_count_note'])
