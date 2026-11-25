"""Display supplied equipment without inventing per-inspection associations."""
import pandas as pd


EQUIPMENT_COLUMNS = ['vehicle_names', 'vehicle_ids', 'trailer_names', 'trailer_ids']


def equipment_summary(records: pd.DataFrame, source_rows=None) -> pd.DataFrame:
    drivers = {}
    if source_rows is not None:
        # Filtered source rows are authoritative for grouped equipment inventories.
        records = records[~records.raw.map(lambda raw: isinstance(raw, dict)
                           and raw.get('sourceFormat') == 'groupedDriver').astype(bool)]
    if source_rows:
        extra = pd.DataFrame([
            {'author_id': str(row['driverID']), 'raw': {'sourceFormat': 'groupedDriver', 'groupedSource': row},
             'vehicle_id': None, 'vehicle_name': None, 'trailer_id': None, 'trailer_name': None}
            for row in source_rows
        ])
        for source in source_rows:
            roster_id = source.get('_roster_driver_id')
            if roster_id and roster_id != str(source.get('driverID')):
                extra.loc[len(extra)] = {'author_id': roster_id,
                    'raw': {'sourceFormat': 'groupedDriver', 'groupedSource': source},
                    'vehicle_id': None, 'vehicle_name': None, 'trailer_id': None, 'trailer_name': None}
        records = pd.concat([records, extra], ignore_index=True)
    for row in records.itertuples(index=False):
        if pd.isna(row.author_id):
            continue
        values = drivers.setdefault(row.author_id, {key: set() for key in EQUIPMENT_COLUMNS})
        raw = row.raw if isinstance(row.raw, dict) else {}
        grouped = raw.get('groupedSource', {}) if raw.get('sourceFormat') == 'groupedDriver' else {}
        for asset in ('vehicle', 'trailer'):
            for field in ('name', 'id'):
                key = f'{asset}_{field}s'
                supplied = grouped.get(f'{asset}{"Names" if field == "name" else "IDs"}', [])
                if isinstance(supplied, list):
                    values[key].update(str(value).strip() for value in supplied
                                       if isinstance(value, (str, int)) and str(value).strip())
                joined = grouped.get(f'{asset}{field.title()}')
                if isinstance(joined, (str, int)) and str(joined).strip():
                    values[key].add(str(joined).strip())
                direct = getattr(row, f'{asset}_{field}')
                if pd.notna(direct) and str(direct).strip():
                    values[key].add(str(direct).strip())
    return pd.DataFrame([
        {'driver_id': driver_id, **{key: ', '.join(sorted(items)) or 'Not supplied'
                                   for key, items in values.items()}}
        for driver_id, values in drivers.items()
    ], columns=['driver_id', *EQUIPMENT_COLUMNS])


def report_vehicle_names(frame, records, source_rows):
    """Add source vehicle context to detail tables without claiming date attribution."""
    if 'vehicle_names' in frame or 'vehicle_names_in_report' in frame:
        return frame
    driver_key = next((key for key in ('driver_id', 'author_id') if key in frame), None)
    if driver_key is None and 'dvir_id' not in frame:
        return frame
    summary = equipment_summary(records, source_rows)
    names = summary.set_index('driver_id').vehicle_names
    if driver_key:
        values = frame[driver_key].map(names)
    else:
        authors = records.drop_duplicates('dvir_id').set_index('dvir_id').author_id
        values = frame.dvir_id.map(authors).map(names)
    output = frame.copy()
    position = output.columns.get_loc(driver_key) + 1 if driver_key else len(output.columns)
    output.insert(position, 'vehicle_names_in_report', values.astype('string').fillna('Not supplied'))
    return output
