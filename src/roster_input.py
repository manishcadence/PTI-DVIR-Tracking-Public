"""Canonicalize roster and unmatched DVIR exports while preserving authorship."""
from .data_adapter import adapt_grouped, identifier, PayloadError


def single_id(value):
    if isinstance(value, list):
        values = list(dict.fromkeys(identifier(x) for x in value if identifier(x)))
        return values[0] if len(values) == 1 else None
    return identifier(value)


def number(value):
    if value is None or value == '':
        return None
    try:
        result = int(value)
        return result if result >= 0 and float(value) == result else None
    except (ValueError,TypeError):
        return None


def adapt_roster(rows):
    if not all(isinstance(row, dict) for row in rows):
        raise PayloadError('Every roster/DVIR row must be a JSON object.')
    canonical, roster = [], {}
    aliases = {'startTimes':('appended_startTIme','appended_startTime'),
               'endTimes':('appended_endTime',), 'vehicleNames':('appended_vehicleName',),
               'trailerIDs':('appended_trailerID',)}
    for index, source in enumerate(rows):
        roster_sid = single_id(source.get('Samsara_DriverID'))
        account_sid = single_id(source.get('samsara_driverId')) or roster_sid
        sid = roster_sid or account_sid
        author_id = single_id(source.get('driverID'))
        tms = identifier(source.get('Tms_ID'))
        in_roster = bool(tms)
        roster_id = (sid or f'tms:{tms}') if in_roster else (author_id or sid or f'unmatched:{index}')
        name = (source.get('Samsara_DriverName') or source.get('Tms_driverName')) if in_roster else (
            source.get('driverName') or source.get('samsara_driverName') or source.get('Samsara_DriverName'))
        if isinstance(name,list):
            name = ', '.join(str(x) for x in name if x)
        name = name or 'Unknown'
        training = str(source.get('PTITraining') or '').strip().lower()
        roster[roster_id] = {'id':roster_id,'name':name,
                            'training_status':'completed' if training in ('done','completed') else 'incomplete' if training=='pti due' else 'unknown',
                            'training_completed_at':source.get('PTITrainingDate') if training in ('done','completed') else None}
        row = {**source, '_roster_driver_id':roster_id, '_is_roster_member':in_roster,
               '_dvir_author_id':author_id, '_status_subject_id':account_sid or author_id,
               '_source_status':source.get('SamsaraStatus'),
               'Samsara_DriverID':sid if in_roster else roster_id,
               'Samsara_DriverName':name,
               'driverID':author_id or roster_id,
               'driverName':source.get('driverName') if author_id else name,
               'samsaraVehicleid':source.get('samsaraVehicleid') or source.get('vehicleID')}
        for field in ('startTimes','endTimes','tripTypes','safetyStatuses','signedBy',
                      'safetyOfficers','vehicleIDs','vehicleNames','trailerIDs','trailerNames'):
            value = source.get(field)
            if value is None:
                for alias in aliases.get(field,()):
                    if source.get(alias) is not None:
                        value = source[alias]
                        break
            if value is not None and not isinstance(value,list):
                raise PayloadError(f'{field} must be a JSON array or null.')
            row[field] = value or []
        if not row['vehicleIDs'] and single_id(source.get('vehicleID')):
            row['vehicleIDs'] = [single_id(source['vehicleID'])]
        if not row['vehicleNames'] and source.get('vehicleName'):
            row['vehicleNames'] = [str(source['vehicleName'])]
        reported = number(source.get('totalPTI'))
        row['totalPTI'] = reported if reported is not None else max(len(row['startTimes']),len(row['endTimes']))
        row['_reported_totalPTI'] = reported
        row['_reported_vehicle_count'] = number(source.get('count_vehicleID',source.get('vehicleCount')))
        row['_reported_trailer_count'] = number(source.get('count_trailerID',source.get('trailerCount')))
        row['_activity_type_unspecified'] = bool(not row['tripTypes'] and any(key in source for key in ('appended_startTIme','appended_startTime')))
        authors = number(source.get('unique_count_driverID'))
        row['_missing_author_detail'] = bool(not author_id and (row['startTimes'] or row['endTimes'] or (reported or 0)>0))
        row['_source_author_ids'] = [identifier(value) for value in source.get('driverID',[]) if identifier(value)] if isinstance(source.get('driverID'),list) else ([author_id] if author_id else [])
        row['_multi_author_aggregate'] = bool((authors is not None and authors > 1) or
                                             (isinstance(source.get('driverID'),list) and author_id is None))
        row['_inspection_alignment_review'] = bool(row['startTimes'] and row['endTimes'] and len(row['startTimes'])!=len(row['endTimes']))
        canonical.append(row)
    dated = [row for row in canonical if row['_dvir_author_id'] and (row['startTimes'] or row['endTimes'])
             and not row['_multi_author_aggregate'] and not row['_inspection_alignment_review']]
    envelope = adapt_grouped(dated)
    matched_ids={row['_roster_driver_id'] for row in canonical if row['_is_roster_member']}
    envelope.drivers = [value for key,value in roster.items() if key in matched_ids]
    envelope.source_rows = canonical
    envelope.roster_complete = True
    envelope.retain_supplied_drivers = True
    envelope.notices.append('Roster membership comes from Tms_ID. Unmatched DVIR authors stay in review. '
                            'SamsaraStatus belongs only to its supplied Samsara driver ID. Multi-author '
                            'aggregates and unaligned arrays do not establish individual inspection credit.')
    return envelope
