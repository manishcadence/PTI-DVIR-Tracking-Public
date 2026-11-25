"""Display export row counts and vehicle/author relationships without collapsing names."""
import pandas as pd

from .data_adapter import identifier


def supplied_count(value):
    return int(value) if type(value) in (int, float) and value >= 0 and int(value) == value else None


def equipment_list_count(source, key):
    return sum(identifier(value) is not None for value in (source.get(key) or []))


def source_associations(rows):
    output = []
    for number, source in enumerate(rows, 1):
        vehicle_count = equipment_list_count(source, 'vehicleIDs')
        trailer_count = equipment_list_count(source, 'trailerIDs')
        output.append({
            'source_row': source.get('_source_row_number', number), 'driver_id': identifier(source.get('driverID')),
            'driver_name': source.get('driverName'),
            'vehicle_id': identifier(source.get('samsaraVehicleid')),
            'vehicle_name': source.get('vehicleName'),
            'vehicle_ids_in_source': ', '.join(map(str, source.get('vehicleIDs') or [])),
            'trailer_ids_in_source': ', '.join(map(str, source.get('trailerIDs') or [])),
            'listed_crew': '; '.join(f"{source.get(f'driverName_{slot}') or 'Unknown'} "
                                    f"(Cogo {source.get(f'cogoID_{slot}') or 'unknown'})"
                                    for slot in range(3)
                                    if source.get(f'cogoID_{slot}') or source.get(f'driverName_{slot}')),
            'source_vehicle_PTIs': vehicle_count, 'source_trailer_PTIs': trailer_count,
            'source_vehicle_plus_trailer_PTIs': vehicle_count + trailer_count
                if vehicle_count is not None and trailer_count is not None else None,
            'source_totalPTI': supplied_count(source.get('totalPTI')),
            'reported_vehicleCount': supplied_count(source.get('vehicleCount')),
            'reported_trailerCount': supplied_count(source.get('trailerCount')),
        })
    columns = ['source_row', 'driver_id', 'driver_name', 'vehicle_id', 'vehicle_name',
               'vehicle_ids_in_source', 'trailer_ids_in_source', 'listed_crew',
               'source_vehicle_PTIs', 'source_trailer_PTIs',
               'source_vehicle_plus_trailer_PTIs', 'source_totalPTI',
               'reported_vehicleCount', 'reported_trailerCount']
    return pd.DataFrame(output, columns=columns)


def source_shared_vehicles(rows):
    """Use source vehicle IDs and DVIR author IDs, not name or crew-name uniqueness."""
    links = []
    for source in rows:
        author_id = identifier(source.get('driverID'))
        if not author_id:
            continue
        vehicles = {identifier(value) for value in source.get('vehicleIDs', [])}
        vehicles.add(identifier(source.get('samsaraVehicleid')))
        for vehicle_id in vehicles - {None}:
            links.append({'vehicle_id': vehicle_id,
                          'vehicle_name': str(source.get('vehicleName') or '')
                              if vehicle_id == identifier(source.get('samsaraVehicleid')) else '',
                          'driver_id': author_id, 'driver_name': str(source.get('driverName') or 'Unknown')})
    columns = ['vehicle_id', 'vehicle_names', 'distinct_DVIR_authors', 'author_ids', 'author_names']
    if not links:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(links).drop_duplicates()
    output = []
    for vehicle_id, group in frame.groupby('vehicle_id'):
        if group.driver_id.nunique() < 2:
            continue
        authors = group[['driver_id', 'driver_name']].drop_duplicates()
        output.append({'vehicle_id': vehicle_id,
                       'vehicle_names': ', '.join(sorted(set(group.vehicle_name) - {''})),
                       'distinct_DVIR_authors': group.driver_id.nunique(),
                       'author_ids': ', '.join(sorted(set(group.driver_id))),
                       'author_names': '; '.join(f'{row.driver_name} ({row.driver_id})'
                                                for row in authors.itertuples(index=False))})
    return pd.DataFrame(output, columns=columns)
