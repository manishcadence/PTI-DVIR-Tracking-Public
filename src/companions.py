"""Show source-listed Cogo companions without inventing inspection-time teams."""
import pandas as pd

from .data_adapter import identifier


COLUMNS = ['driver_id', 'driver_name', 'vehicle_id', 'vehicle_name', 'cogo_slot',
           'cogo_id', 'listed_driver_name', 'relationship', 'source_samsara_driver_id']


def listed_companions(source_rows):
    output = []
    for source in source_rows:
        author_id = identifier(source.get('driverID'))
        author_name = str(source.get('driverName') or '').strip()
        slots = [(i, identifier(source.get(f'cogoID_{i}')), str(source.get(f'driverName_{i}') or '').strip())
                 for i in range(3)]
        slots = [(i, cid, name) for i, cid, name in slots if cid or name]
        own = [i for i, _, name in slots if name and name.casefold() == author_name.casefold()]
        if len(slots) < 2:
            continue
        for slot, cogo_id, name in slots:
            if len(own) == 1 and slot == own[0]:
                continue
            output.append({
                'driver_id': author_id, 'driver_name': author_name,
                'vehicle_id': identifier(source.get('samsaraVehicleid')),
                'vehicle_name': source.get('vehicleName'), 'cogo_slot': slot,
                'cogo_id': cogo_id, 'listed_driver_name': name or 'Unknown',
                'relationship': 'Listed companion · timing and identity unverified' if len(own) == 1
                                else 'Vehicle crew · author mapping needs review',
                'source_samsara_driver_id': identifier(source.get('SamsaraDriverId')),
            })
    return pd.DataFrame(output, columns=COLUMNS).drop_duplicates()


def companion_summary(source_rows):
    rows = listed_companions(source_rows)
    if rows.empty:
        return pd.DataFrame(columns=['driver_id', 'cogo_listed_companions'])
    rows['label'] = rows.listed_driver_name + ' (Cogo ' + rows.cogo_id.fillna('unknown ID') + ')'
    return rows.groupby('driver_id', as_index=False).agg(
        cogo_listed_companions=('label', lambda values: '; '.join(sorted(set(values)))))


def companion_activity(data, dates, source_rows=None):
    """Match listed names within source vehicle context; report each author's own activity."""
    from .analytics import recorded_inspections
    from .source_associations import supplied_count, equipment_list_count
    rows = listed_companions(data.source_rows if source_rows is None else source_rows).copy()
    dated = data.dvir_records[data.dvir_records.inspection_date.isin(dates)]
    totals = dated.groupby('author_id').dvir_id.nunique()
    ptis = recorded_inspections(dated).groupby('author_id').dvir_id.nunique()
    history = data.dvir_records[data.dvir_records.inspection_time.notna() &
                                data.dvir_records.inspection_date.le(dates[-1])]
    last = history.groupby('author_id').inspection_date.max()
    matches, status = [], []
    source_counts = {key: [] for key in ('vehicleCount', 'trailerCount', 'totalPTI')}
    for row in rows.itertuples(index=False):
        candidates = set()
        for source in data.source_rows:
            if str(source.get('driverName') or '').strip().casefold() != row.listed_driver_name.casefold():
                continue
            vehicles = {identifier(value) for value in source.get('vehicleIDs', [])}
            vehicles.add(identifier(source.get('samsaraVehicleid')))
            if row.vehicle_id is not None and row.vehicle_id in vehicles:
                driver_id = identifier(source.get('driverID'))
                if driver_id and driver_id != row.driver_id:
                    candidates.add(driver_id)
        matches.append(next(iter(candidates)) if len(candidates) == 1 else None)
        status.append('Source name and vehicle match' if len(candidates) == 1 else
                      'Multiple source IDs match · review' if candidates else 'No matching DVIR author in source')
        matched_id = matches[-1]
        for key in source_counts:
            values = set()
            if matched_id is not None:
                for source in data.source_rows:
                    if identifier(source.get('driverID')) != matched_id:
                        continue
                    vehicles = {identifier(value) for value in source.get('vehicleIDs', [])}
                    vehicles.add(identifier(source.get('samsaraVehicleid')))
                    if row.vehicle_id in vehicles:
                        values.add(equipment_list_count(source, 'vehicleIDs') if key == 'vehicleCount'
                                   else equipment_list_count(source, 'trailerIDs') if key == 'trailerCount'
                                   else supplied_count(source.get(key)))
            source_counts[key].append(next(iter(values)) if len(values) == 1 else None)
    rows['co_driver_id_from_source'] = matches
    rows['co_driver_match'] = status
    for key, title in [('vehicleCount', 'co_driver_source_vehicle_PTIs'),
                       ('trailerCount', 'co_driver_source_trailer_PTIs'),
                       ('totalPTI', 'co_driver_source_totalPTI')]:
        rows[title] = pd.array(source_counts[key], dtype='Int64')
    rows['co_driver_source_vehicle_plus_trailer_PTIs'] = (
        rows.co_driver_source_vehicle_PTIs + rows.co_driver_source_trailer_PTIs)
    rows['driver_DVIRs_in_selected_window'] = rows.driver_id.map(totals).fillna(0).astype(int)
    rows['co_driver_DVIRs_in_selected_window'] = rows.co_driver_id_from_source.map(totals).astype('Int64')
    rows['co_driver_pre_post_trips_in_selected_window'] = rows.co_driver_id_from_source.map(ptis).astype('Int64')
    # A successfully matched driver with no activity contributes an explicit zero.
    matched = rows.co_driver_id_from_source.notna()
    for column in ('co_driver_DVIRs_in_selected_window', 'co_driver_pre_post_trips_in_selected_window'):
        rows.loc[matched, column] = rows.loc[matched, column].fillna(0)
    rows['co_driver_last_inspection_date'] = rows.co_driver_id_from_source.map(last)
    return rows
