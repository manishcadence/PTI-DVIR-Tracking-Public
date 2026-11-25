"""Session-only interpretation of roster, primary and explicit CODRIVER DVIR blocks."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import re
import pandas as pd


class UploadError(ValueError):
    pass


def sid(value):
    return str(value).strip() or None if isinstance(value,(str,int)) and not isinstance(value,bool) else None


def count(value):
    if value is None or value=='': return None
    if isinstance(value,bool): return None
    try:
        n=int(value)
        return n if n>=0 and float(value)==n else None
    except (ValueError,TypeError): return None


def status(value):
    text=str(value or '').strip().casefold()
    return 'Active' if text in ('active','activated') else 'Deactivated' if text in ('deactive','deactivated','inactive') else 'Unknown'


def training_status(value):
    """User rule: only DONE establishes completed PTI training."""
    return 'Done' if isinstance(value,str) and value.strip().casefold()=='done' else 'Not done'


def safety_values(value):
    """Keep supplied grouped values without assuming per-date attribution."""
    if isinstance(value,list):
        return set().union(*(safety_values(item) for item in value))
    if not isinstance(value,str) or not value.strip():return set()
    text=value.strip()
    if text.startswith('['):
        try:return safety_values(json.loads(text))
        except ValueError:pass
    return {{'safe':'Safe','unsafe':'Unsafe','resolved':'Resolved'}.get(text.casefold(),text)}


def preferred_safety(values):
    for label in ('Unsafe','Resolved'):
        if label in values:return label
    other=sorted(values-{'Safe'},key=str.casefold)
    return other[0] if other else 'Safe' if 'Safe' in values else 'Not supplied'


def dates(value):
    output=set()
    for value in (value if isinstance(value,list) else re.findall(r'\d{4}-\d{2}-\d{2}',str(value or ''))):
        try: output.add(datetime.fromisoformat(str(value)[:10]).date())
        except ValueError: pass
    return output


def array(row,key,aliases=()):
    value=row.get(key)
    if value is None:
        value=next((row[k] for k in aliases if row.get(k) is not None),None)
    if value is None: return []
    if not isinstance(value,list): raise UploadError(f'{key} must be a JSON array or null.')
    return value


@dataclass
class UploadReport:
    people: pd.DataFrame
    events: pd.DataFrame
    teams: pd.DataFrame
    blocks: pd.DataFrame
    issues: pd.DataFrame
    timezone: str
    latest: object
    earliest: object
    source_rows: int


def parse_upload(contents,timezone='America/Chicago'):
    try: payload=json.loads(contents)
    except (ValueError,UnicodeError): raise UploadError('This file is not valid JSON.') from None
    if isinstance(payload,dict):
        rows=next((payload[k] for k in ('data','driverSummaries','drivers','inspections') if isinstance(payload.get(k),list)),None)
        if rows is None and any(k in payload for k in ('Tms_ID','driverID','Samsara_DriverID')): rows=[payload]
    else: rows=payload
    if not isinstance(rows,list) or not all(isinstance(row,dict) for row in rows):
        raise UploadError('Upload a JSON array of driver rows, or an object containing data/driverSummaries.')
    people={}; events={}; blocks={}; team_groups={}; issues=[]; statuses=defaultdict(set); cogo=defaultdict(set); evidence=set(); training=defaultdict(set); training_dates=defaultdict(set); incomplete_training=set()
    dual=any(any(key.startswith('CODRIVER_') for key in row) for row in rows)
    def issue(level,check,row,person,detail):
        issues.append({'severity':level,'check':check,'source_row':row,'driver_id':person,'detail':detail})
    def person(key,name,roster=False,source=None):
        if not key: return
        p=people.setdefault(key,{'driver_id':key,'driver_name':name or 'Unknown','in_roster':False,
                               'tms_id':None,'cogo_id':None,'holidays':set(),'holiday_data_available':False,'vehicles':set(),'trailers':set(),
                               'phone':None,'license_number':None,'state':None,'has_crew':False,'identity_review':False})
        if name and (p['driver_name']=='Unknown' or roster): p['driver_name']=str(name)
        if roster: p['in_roster']=True
        if source:
            if roster:
                p.update(tms_id=source.get('Tms_ID'),cogo_id=source.get('COGOELD'),
                         phone=source.get('Samsara_Phone') or source.get('Tms_phone'),
                         license_number=source.get('Samsara_licenseNumber') or source.get('Tms_licenseNumber'),
                         state=source.get('Samsara_state') or source.get('Tms_state'))
                holiday_dates=dates(source.get('appended_status_date'))
                p['holidays'].update(holiday_dates)
                # Equipment context remains visible even without an inspection.
                if source.get('vehicleName'):
                    p['vehicles'].add(str(source['vehicleName']))
                holiday_count=count(source.get('count_status_date'))
                if holiday_dates or holiday_count==0 or (source.get('appended_status_date')==[] and holiday_count is None):
                    p['holiday_data_available']=True
            lookup=sid(source.get('samsara_driverId'))
            if lookup==key:
                p['phone']=p['phone'] or source.get('samsara_phoneNumber')
                p['license_number']=p['license_number'] or source.get('samsara_licenseNumber')
                p['state']=p['state'] or source.get('samsara_State')
        return p
    owners={}
    for n,row in enumerate(rows,1):
        roster=bool(sid(row.get('Tms_ID')))
        key=sid(row.get('Samsara_DriverID')) if roster else sid(row.get('driverID')) or sid(row.get('samsara_driverId'))
        key=key or (f'tms:{row["Tms_ID"]}' if roster else f'unmatched-row:{n}')
        owners[n]=key
        # Primary training belongs to the roster identity, never an overwritten lookup ID.
        if 'PTITraining' in row:
            raw=row.get('PTITraining')
            training[key].add(training_status(raw))
            if raw is False or str(raw or '').strip().casefold().replace('_',' ') in ('not','not done','not completed','incomplete','no','false','pending'):
                incomplete_training.add(key)
        training_dates[key].update(dates(row.get('PTITrainingDate')))
        training_partner=sid(row.get('CODRIVER_driverID'))
        if training_partner:
            if 'CODRIVER_PTITraining' in row:
                raw=row.get('CODRIVER_PTITraining')
                training[training_partner].add(training_status(raw))
                if raw is False or str(raw or '').strip().casefold().replace('_',' ') in ('not','not done','not completed','incomplete','no','false','pending'):
                    incomplete_training.add(training_partner)
            training_dates[training_partner].update(dates(row.get('CODRIVER_PTITrainingDate')))
        name=(row.get('Samsara_DriverName') or row.get('Tms_driverName')) if roster else row.get('driverName') or row.get('samsara_driverName')
        person(key,name,roster,row)
        if roster and not sid(row.get('Samsara_DriverID')):
            people[key]['identity_review']=True
            issue('Review','Roster Samsara ID missing',n,key,'Driver retained under TruckMate ID; no partner ID is substituted.')
        cid=sid(row.get('COGOELD'))
        if cid: cogo[cid].add(key)
        partner=sid(row.get('CODRIVER_driverID'))
        if partner:
            person(partner,row.get('CODRIVER_driverName'),False,row)
            slot=row.get('matched_on')
            partner_cogo=sid(row.get(slot)) if isinstance(slot,str) and slot in ('cogoID_0','cogoID_1','cogoID_2') else None
            if partner_cogo: cogo[partner_cogo].add(partner)
        lookup=sid(row.get('samsara_driverId'))
        if not lookup and (not partner or partner==key): lookup=sid(row.get('Samsara_DriverID')) or sid(row.get('driverID'))
        label=status(row.get('SamsaraStatus'))
        if lookup and label!='Unknown': statuses[lookup].add(label)
    safety_by_author=defaultdict(set)
    def add_block(row,n,prefix,key,name,role):
        for field in ('safetyStatus','safetyStatuses','appended_safetyStatus','appended_safetyStatuses','safety_status'):
            safety_by_author[key].update(safety_values(row.get(prefix+field)))
        starts=array(row,prefix+'appended_startTIme',(prefix+'appended_startTime',) if prefix else ('appended_startTime','startTimes'))
        ends=array(row,prefix+'appended_endTime',() if prefix else ('endTimes',))
        total=count(row.get(prefix+'totalPTI'))
        vehicle_count=count(row.get(prefix+'count_vehicleID',row.get('vehicleCount') if not prefix else None))
        trailer_count=count(row.get(prefix+'count_trailerID',row.get('trailerCount') if not prefix else None))
        if total is None and vehicle_count is None and trailer_count is None and not starts and not ends: return None
        vehicles=array(row,prefix+'appended_vehicleName',() if prefix else ('vehicleNames',))
        trailers=array(row,prefix+'appended_trailerID',() if prefix else ('trailerIDs',))
        person(key,name,False,row)
        people[key]['vehicles'].update(str(x) for x in vehicles if x)
        people[key]['trailers'].update(str(x) for x in trailers if x)
        size=max(len(starts),len(ends))
        if size or any((value or 0)>0 for value in (total,vehicle_count,trailer_count)): evidence.add(key)
        a=pd.to_datetime(pd.Series(starts,dtype='object').reindex(range(size)),utc=True,errors='coerce',format='mixed')
        b=pd.to_datetime(pd.Series(ends,dtype='object').reindex(range(size)),utc=True,errors='coerce',format='mixed')
        time=a.fillna(b)
        block_id=hashlib.sha256(json.dumps([key,a.astype(str).tolist(),b.astype(str).tolist()],sort_keys=True).encode()).hexdigest()
        block={'block_id':block_id,'driver_id':key,'source_block':role,'source_row':n,
               'reported_vehicle_count':vehicle_count,'reported_trailer_count':trailer_count,'reported_totalPTI':total,
               'timestamp_pairs':size,'vehicle_names':', '.join(sorted(set(str(x) for x in vehicles if x))) or 'Not supplied',
               'trailer_ids':', '.join(sorted(set(str(x) for x in trailers if x))) or 'Not supplied'}
        if block_id in blocks:
            old=blocks[block_id]
            for field in ('reported_vehicle_count','reported_trailer_count','reported_totalPTI'):
                if old[field] is not None and block[field] is not None and old[field]!=block[field]:
                    old[field]=None; issue('Review','Conflicting reported counts',n,key,'Repeated history has different reported totals; no extra inspections are invented.')
        else: blocks[block_id]=block
        if starts and ends and len(starts)!=len(ends):
            issue('Review','Start/end array lengths differ',n,key,'Dates remain visible; missing endpoints are not paired with another inspection.')
        if size==0 and any((value or 0)>0 for value in (total,vehicle_count,trailer_count)):
            issue('Review','Counts supplied without inspection dates',n,key,'Source counts show DVIR evidence, but dates are unavailable.')
        if total is not None and total!=size:
            issue('Review','Reported count differs from timestamps',n,key,f'Reported PTI {total}; supplied timestamp entries {size}.')
        if total is not None and vehicle_count is not None and trailer_count is not None and total!=vehicle_count+trailer_count:
            issue('Review','Equipment counts differ from totalPTI',n,key,'Vehicle plus trailer counts do not equal totalPTI.')
        if count(row.get(prefix+'unique_count_driverID')) not in (None,1):
            issue('Review','Block contains multiple driver IDs',n,key,'Aggregate author attribution needs confirmation.')
        occurrence=defaultdict(int)
        block_keys=set()
        for index in range(size):
            start,end,stamp=a.iloc[index],b.iloc[index],time.iloc[index]
            pair=(str(start),str(end)); occurrence[pair]+=1
            event_key=hashlib.sha256(json.dumps([key,*pair,occurrence[pair],block_id if pd.isna(stamp) else '']).encode()).hexdigest()
            block_keys.add(event_key)
            review=pd.isna(stamp) or (pd.notna(start) and pd.notna(end) and end<start)
            if review: issue('Review','Inspection timestamp needs review',n,key,'Timestamp is missing/invalid or inspection end precedes start.')
            minutes=(end-start).total_seconds()/60 if pd.notna(start) and pd.notna(end) and end>=start else None
            if event_key not in events:
                events[event_key]={'record_key':event_key,'driver_id':key,'driver_name':people[key]['driver_name'],
                    'inspection_time':stamp,'inspection_date':stamp.tz_convert(timezone).date() if pd.notna(stamp) else None,
                    'start_time':start,'end_time':end,'duration_minutes':minutes,'source_block':role,
                    'vehicle_names_in_report':block['vehicle_names'],'trailer_ids_in_report':block['trailer_ids'],
                    'needs_review':bool(review),'source_row':n}
        blocks[block_id].setdefault('_event_keys',set()).update(block_keys)
        return block_id
    for n,row in enumerate(rows,1):
        owner=owners[n]; primary_roster=bool(sid(row.get('Tms_ID')))
        author=owner if primary_roster and dual else sid(row.get('driverID')) or owner
        name=(row.get('Samsara_DriverName') or row.get('Tms_driverName')) if author==owner else row.get('driverName')
        main=add_block(row,n,'',author,name,'Primary DVIR' if primary_roster and dual else 'Uploaded DVIR')
        partner=sid(row.get('CODRIVER_driverID'))
        if partner: add_block(row,n,'CODRIVER_',partner,row.get('CODRIVER_driverName'),'Co-driver DVIR')
        if primary_roster and dual and sid(row.get('driverID')) and sid(row.get('driverID'))!=owner:
            issue('Information','Lookup ID differs from primary roster ID',n,owner,'The generic lookup driverID is not used to classify the primary DVIR block; CODRIVER identity remains separate.')
        if main and primary_roster and row.get('driverName'):
            normalize=lambda x:' '.join(str(x or '').casefold().split())
            if normalize(row['driverName'])!=normalize(people[owner]['driver_name']):
                people[owner]['identity_review']=True
                issue('Review','Primary DVIR name differs from roster',n,owner,'Check the source identity mapping; primary and partner IDs remain separate.')
        slots=[(sid(row.get(f'cogoID_{i}')),str(row.get(f'driverName_{i}') or '').strip()) for i in range(3)]
        slots=list(dict.fromkeys((cid,name) for cid,name in slots if cid or name))
        has_crew=bool(row.get('vehicleName') and len(slots)>=2) or bool(partner and row.get('matched_on'))
        if has_crew:
            cids=sorted({cid for cid,_ in slots if cid})
            group_key='crew:'+hashlib.sha256(json.dumps(cids or [owner,partner,n]).encode()).hexdigest()[:12]
            group=team_groups.setdefault(group_key,{'crew_id':group_key,'members':set(),'roster_ids':set(),
                'crew_names':set(),'cogo_ids':set(),'vehicles':set(),'unmapped':set(),'source_rows':set()})
            group['members'].add(owner); people[owner]['has_crew']=True
            if main and author!=owner:
                group['members'].add(author);people[author]['has_crew']=True
            if primary_roster: group['roster_ids'].add(owner)
            if partner: group['members'].add(partner);people[partner]['has_crew']=True
            for cid,slot_name in slots:
                if cid:
                    group['cogo_ids'].add(cid)
                    candidates=cogo.get(cid,set())
                    if len(candidates)==1:
                        member=next(iter(candidates));group['members'].add(member);people[member]['has_crew']=True
                    else:
                        group['unmapped'].add(f'{slot_name or "Unknown"} (Cogo {cid})')
                if slot_name: group['crew_names'].add(slot_name)
            if row.get('vehicleName'): group['vehicles'].add(str(row['vehicleName']))
            group['source_rows'].add(n)
            slot=row.get('matched_on')
            if partner and isinstance(slot,str) and sid(row.get('COGOELD'))==sid(row.get(slot)):
                issue('Review','Partner slot points to roster driver',n,owner,'matched_on should identify the partner slot in this export.')
        if primary_roster and row.get('count_status_date') is not None and count(row['count_status_date'])!=len(dates(row.get('appended_status_date'))):
            issue('Review','Holiday count differs from dates',n,owner,'Calendar calculations use the distinct supplied holiday dates.')
    by_author=defaultdict(list)
    for block in blocks.values():
        by_author[block['driver_id']].append(block)
        block['counted_in_totals']=True
        block['_counts_review']=False
    for author,source_blocks in by_author.items():
        selected=set();review_counts=False
        for block in sorted(source_blocks,key=lambda b:len(b.get('_event_keys',set())),reverse=True):
            keys=block.get('_event_keys',set())
            if keys and keys.issubset(selected):
                block['counted_in_totals']=False
                issue('Information','Subset history counted once',block['source_row'],author,'A repeated subset of this person’s records does not add inspection totals.')
            elif keys & selected:
                review_counts=True
            selected.update(keys)
        if review_counts:
            for block in source_blocks:block['_counts_review']=True
            issue('Review','Overlapping histories need equipment count review',None,author,'Dated records are deduplicated; overlapping source counts cannot safely be added.')
    event_frame=pd.DataFrame(list(events.values()),columns=['record_key','driver_id','driver_name','inspection_time','inspection_date',
        'start_time','end_time','duration_minutes','source_block','vehicle_names_in_report','trailer_ids_in_report','needs_review','source_row'])
    for field in ('inspection_time','start_time','end_time'):
        event_frame[field]=pd.to_datetime(event_frame[field],utc=True,errors='coerce')
    team_rows=[]
    memberships=defaultdict(int)
    for group in team_groups.values():
        for key in group['members']: memberships[key]+=1
    for group in team_groups.values():
        team_rows.append({**group,'multiple_crew_membership':any(memberships[x]>1 for x in group['members'])})
    identity_ids={key for key,value in people.items() if value['identity_review']}
    event_frame['needs_review']=event_frame.needs_review.fillna(False).astype(bool) | event_frame.driver_id.isin(identity_ids)
    reviewed_ids={entry['driver_id'] for entry in issues if entry['severity']=='Review'}
    for key,p in people.items():
        p['has_data_review']=key in reviewed_ids
        supplied=training[key]
        p['pti_training_status']='Done' if supplied=={'Done'} else 'Not done'
        p['training_explicitly_incomplete']=key in incomplete_training
        p['pti_training_date']=', '.join(day.isoformat() for day in sorted(training_dates[key])) or 'Not supplied'
        p['training_completed_date']=next(iter(training_dates[key])) if len(training_dates[key])==1 else None
        p['training_date_conflict']=len(training_dates[key])>1
        if len(supplied)>1:
            p['has_data_review']=True
            issue('Review','Conflicting PTI training status',None,key,'Uploaded training values disagree; completion remains unconfirmed.')
        values=statuses.get(key,set())
        p['samsara_status']=next(iter(values)) if len(values)==1 else 'Unknown'
        if len(values)>1: issue('Review','Conflicting Samsara status',None,key,'Account status remains Unknown.')
        p['vehicle_names']=', '.join(sorted(p.pop('vehicles'))) or 'Not supplied'
        p['trailer_ids']=', '.join(sorted(p.pop('trailers'))) or 'Not supplied'
        p['arrangement']='Co-driver' if p['has_crew'] else 'Solo / no crew information'
        p['safety_status_file']=preferred_safety(safety_by_author[key])
        p['safety_values_file']=', '.join(sorted(safety_by_author[key])) or 'Not supplied'
        p['source_has_own_DVIR']=key in evidence
        p['source_category']='Outside primary roster' if not p['in_roster'] else 'Co-driver' if p['has_crew'] else 'Solo with DVIR' if key in evidence else 'Solo without DVIR'
    valid=event_frame.inspection_time.dropna()
    latest=valid.max().tz_convert(timezone).date() if len(valid) else datetime.now(ZoneInfo(timezone)).date()
    earliest=valid.min().tz_convert(timezone).date() if len(valid) else latest
    return UploadReport(pd.DataFrame(list(people.values())),event_frame,pd.DataFrame(team_rows),
        pd.DataFrame(list(blocks.values()),columns=['block_id','driver_id','source_block','source_row','reported_vehicle_count','reported_trailer_count',
        'reported_totalPTI','timestamp_pairs','vehicle_names','trailer_ids','counted_in_totals','_counts_review','_event_keys']),pd.DataFrame(issues,columns=['severity','check','source_row','driver_id','detail']),
        timezone,latest,earliest,len(rows))


def reported_rollup(report):
    rows=[]
    fields=('reported_vehicle_count','reported_trailer_count','reported_totalPTI')
    for key,group in report.blocks.groupby('driver_id'):
        selected=group[group.counted_in_totals]
        values={'driver_id':key}
        for field in fields:
            values[field]=None if group._counts_review.any() or selected[field].isna().any() else selected[field].sum(min_count=1)
        rows.append(values)
    return pd.DataFrame(rows,columns=['driver_id',*fields])


def people_summary(report,window,end):
    frame=report.people.copy()
    if frame.empty: return frame
    dated=report.events[report.events.inspection_time.notna() & report.events.inspection_date.le(end)]
    selected=dated[dated.inspection_date.isin(window)]
    counts=selected.groupby('driver_id').size();days=selected.groupby('driver_id').inspection_date.nunique()
    last=dated.groupby('driver_id').inspection_date.max()
    frame['dated_PTIs']=frame.driver_id.map(counts).fillna(0).astype(int)
    frame['recorded_dates']=frame.driver_id.map(days).fillna(0).astype(int)
    frame['last_done']=frame.driver_id.map(last)
    frame['has_own_DVIR']=frame.source_has_own_DVIR
    def training_period(row):
        day=row.training_completed_date
        if row.training_date_conflict:return 'Training dates need review'
        if row.training_explicitly_incomplete:return 'Not trained'
        if row.pti_training_status=='Needs review':return 'Training status needs review'
        if day is not None and day>end:return 'Trained after period' if row.pti_training_status=='Done' else 'Training dated after period'
        if day==end:return 'Training on report-ending date'
        if row.pti_training_status!='Done':return 'Training not recorded'
        if day is None:return 'Training date unknown'
        return 'Trained before period' if day<min(window) else 'Trained during period'
    frame['training_period_status']=frame.apply(training_period,axis=1)
    frame['training_followup_eligible']=~frame.training_period_status.isin(['Not trained','Trained after period','Training dated after period','Training on report-ending date'])
    frame['post_training_dates']=[{day for day in window if r.training_completed_date is None or day>r.training_completed_date}
                                  if r.training_followup_eligible else set() for r in frame.itertuples()]
    frame['days_since_last']=[(end-d).days if pd.notna(d) else None for d in frame.last_done]
    frame['holiday_on_report_date']=frame.holidays.map(lambda values:end in values)
    frame['consistency']=frame.recorded_dates.map(lambda n:'Regular' if n>=(len(window)+1)//2 else 'Intermittent' if n else 'No record in period')
    frame['holiday_dates_in_period']=frame.holidays.map(lambda values:len(set(window)&values))
    frame['holiday_dates_display']=frame.holidays.map(lambda values:', '.join(day.isoformat() for day in sorted(set(window)&values)) or 'None reported')
    frame['availability']=frame.apply(lambda r:'On holiday all period' if r.holiday_dates_in_period==len(window) else 'Partly on holiday' if r.holiday_dates_in_period else 'No holiday dates reported' if r.holiday_data_available else 'Unknown',axis=1)
    recorded=selected.groupby('driver_id').inspection_date.agg(set).to_dict()
    frame['nonholiday_dates_without_record']=[len(r.post_training_dates-r.holidays-recorded.get(r.driver_id,set())) for r in frame.itertuples()]
    frame['on_selected_date']=frame.driver_id.isin(set(selected.loc[selected.inspection_date.eq(end),'driver_id']))
    peers=defaultdict(set)
    for group in report.teams.to_dict('records'):
        for key in group['members']: peers[key].update(group['members']-{key})
    frame['partner_PTIs_in_period']=frame.driver_id.map(lambda key:sum(int(counts.get(other,0)) for other in peers.get(key,set())))
    evidence_ids=set(frame.loc[frame.has_own_DVIR,'driver_id'])
    valid_dates=report.events[report.events.inspection_time.notna()].groupby('driver_id').inspection_date.agg(set).to_dict()
    frame['has_partner_DVIR']=frame.driver_id.map(lambda key:bool(peers.get(key,set()) & evidence_ids))
    frame['has_covered_DVIR']=frame.has_own_DVIR | frame.has_partner_DVIR
    frame['last_covered_dvir_in_file']=frame.driver_id.map(lambda key:max((day for member in {key}|peers.get(key,set()) for day in valid_dates.get(member,set())),default=None))
    frame['dvir_coverage']=frame.apply(lambda r:'Own DVIR' if r.has_own_DVIR else 'Co-driver DVIR' if r.has_partner_DVIR else 'No own or co-driver DVIR',axis=1)
    frame['coverage_dates']=frame.driver_id.map(lambda key:set().union(*(recorded.get(member,set()) for member in {key}|peers.get(key,set()))))
    frame['covered_dates_in_period']=frame.coverage_dates.map(len)
    frame['coverage_dates_without_recorded_holiday']=[len(r.post_training_dates-r.holidays-r.coverage_dates) for r in frame.itertuples()]
    frame['covered_on_selected_date']=frame.coverage_dates.map(lambda values:end in values)
    frame['coverage_consistency']=frame.covered_dates_in_period.map(lambda n:'Regular' if n>=(len(window)+1)//2 else 'Intermittent' if n else 'No record in period')
    coverage_valid=frame.driver_id.map(lambda key:any(valid_dates.get(member,set()) for member in {key}|peers.get(key,set())))
    frame.loc[frame.has_covered_DVIR & ~coverage_valid,'coverage_consistency']='Needs date detail'
    flagged=set(report.events.loc[report.events.needs_review.fillna(False),'driver_id'])
    frame['needs_review']=frame.identity_review | frame.has_data_review | frame.driver_id.isin(flagged)
    totals=reported_rollup(report)
    frame=frame.merge(totals,on='driver_id',how='left')
    valid_ids=set(report.events.loc[report.events.inspection_time.notna(),'driver_id'])
    frame.loc[frame.has_own_DVIR & ~frame.driver_id.isin(valid_ids),'consistency']='Needs date detail'
    excluded=~frame.training_followup_eligible
    frame.loc[excluded & frame.dated_PTIs.eq(0),'consistency']=frame.loc[excluded & frame.dated_PTIs.eq(0),'training_period_status']
    frame.loc[excluded & frame.covered_dates_in_period.eq(0),'coverage_consistency']=frame.loc[excluded & frame.covered_dates_in_period.eq(0),'training_period_status']
    frame.loc[excluded & ~frame.has_covered_DVIR,'dvir_coverage']=frame.loc[excluded & ~frame.has_covered_DVIR,'training_period_status']
    frame['training_done_no_dvir_in_period']=frame.pti_training_status.eq('Done') & frame.training_followup_eligible & frame.dated_PTIs.eq(0)
    frame['training_done_no_dvir_in_file']=frame.pti_training_status.eq('Done') & frame.training_followup_eligible & ~frame.has_own_DVIR
    frame['category']=frame.source_category
    return frame


def crew_summary(report,window,end):
    rows=[]
    selected=report.events[report.events.inspection_date.isin(window)]
    people=people_summary(report,window,end).set_index('driver_id') if not report.people.empty else pd.DataFrame()
    rollup=reported_rollup(report)
    for group in report.teams.to_dict('records'):
        members=group['members'];own=selected[selected.driver_id.isin(members)]
        block=rollup[rollup.driver_id.isin(members)]
        total=lambda field:None if block[field].isna().any() else block[field].sum(min_count=1)
        states={people.loc[key,'samsara_status'] for key in members}
        done_dates=set(own.inspection_date.dropna())
        evaluated=group['roster_ids'] or members
        eligible=any(people.loc[key,'training_followup_eligible'] for key in evaluated)
        count_by=own.groupby('driver_id').size()
        rows.append({'crew_id':group['crew_id'],'team_members':'; '.join(f'{people.loc[key,"driver_name"]} ({key})' for key in sorted(members)),
            'vehicle_names':', '.join(sorted(group['vehicles'])) or 'Not supplied',
            'samsara_status':next(iter(states)) if len(states)==1 else 'Mixed',
            'member_statuses':'; '.join(f'{people.loc[key,"driver_name"]}: {people.loc[key,"samsara_status"]}' for key in sorted(members)),
            'dated_PTIs':len(own),'recorded_dates':len(done_dates),
            'consistency':'Regular' if len(done_dates)>=(len(window)+1)//2 else 'Intermittent' if done_dates else 'No record in period' if eligible else 'Not assessed · training',
            'member_training':'; '.join(f'{people.loc[key,"driver_name"]}: {people.loc[key,"training_period_status"]} ({people.loc[key,"pti_training_date"]})' for key in sorted(members)),
            'member_safety':'; '.join(f'{people.loc[key,"driver_name"]}: {people.loc[key,"safety_status_file"]}' for key in sorted(members)),
            'each_person_own_PTIs':'; '.join(f'{people.loc[key,"driver_name"]}: {int(count_by.get(key,0))}' for key in sorted(members)),
            'reported_vehicle_count':total('reported_vehicle_count'),'reported_trailer_count':total('reported_trailer_count'),
            'reported_totalPTI':total('reported_totalPTI'),'last_done':report.events.loc[report.events.driver_id.isin(members) & report.events.inspection_date.le(end),'inspection_time'].max(),
            'known_duration_minutes':own.duration_minutes.sum(min_count=1),'duration_records':int(own.duration_minutes.notna().sum()),
            'unmapped_crew_members':'; '.join(sorted(group['unmapped'])),'multiple_crew_membership':group['multiple_crew_membership'],
            'members':members,'roster_ids':group['roster_ids'],'source_rows':group['source_rows'],
            'needs_review':bool(group['unmapped']) or group['multiple_crew_membership'] or any(people.loc[key,'has_data_review'] for key in members)})
    return pd.DataFrame(rows)
