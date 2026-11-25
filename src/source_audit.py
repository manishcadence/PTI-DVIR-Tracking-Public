"""Explain repeated driver IDs and preserve source-row provenance."""
from collections import defaultdict
import json

import pandas as pd


def duplicate_drivers(rows):
    grouped = defaultdict(list)
    for number, row in enumerate(rows, 1):
        grouped[str(row.get('driverID'))].append((number, row))
    output = []
    for driver_id, entries in grouped.items():
        if len(entries) < 2:
            continue
        fields = set().union(*(row for _, row in entries))
        differing = sorted(key for key in fields if len({json.dumps(row.get(key), sort_keys=True)
                                                        for _, row in entries}) > 1)
        histories = {json.dumps([row.get('startTimes'), row.get('endTimes')], sort_keys=True)
                     for _, row in entries}
        output.append({'driver_id': driver_id,
                       'driver_name': ' / '.join(sorted({str(row.get('driverName') or 'Unknown')
                                                         for _, row in entries})),
                       'source_rows': len(entries),
                       'source_row_numbers': ', '.join(str(number) for number, _ in entries),
                       'distinct_timestamp_histories': len(histories),
                       'differing_fields': ', '.join(differing) or 'Identical rows'})
    columns = ['driver_id', 'driver_name', 'source_rows', 'source_row_numbers',
               'distinct_timestamp_histories', 'differing_fields']
    return pd.DataFrame(output, columns=columns).sort_values('driver_name', key=lambda value: value.str.casefold())
