"""Presentation-ready fleet trends and follow-up groups."""
import pandas as pd

from .analytics import recorded_inspections
from .filters import officer_key, officer_labels
from .source_associations import source_associations


def driver_pti_totals(drivers, source_rows):
    """Keep source equipment entry totals separate from reported totalPTI metadata."""
    associations = source_associations(source_rows)
    fields = ['source_vehicle_PTIs', 'source_trailer_PTIs', 'source_totalPTI']
    totals = associations.groupby('driver_id')[fields].sum()
    output = drivers[['driver_id', 'driver_name']].merge(totals, on='driver_id', how='left')
    output[fields] = output[fields].fillna(0).astype(int)
    output['combined_equipment_PTIs'] = output.source_vehicle_PTIs + output.source_trailer_PTIs
    output['has_supplied_evidence'] = output.combined_equipment_PTIs.gt(0) | output.source_totalPTI.gt(0)
    return output


def daily_participation(scope):
    accepted = recorded_inspections(scope.records)
    accepted = accepted[accepted.author_id.isin(scope.drivers.driver_id)]
    observed = accepted.groupby('inspection_date').author_id.nunique()
    return pd.DataFrame([{'date': day, 'Recorded': int(observed.get(day, 0)),
                          'No record': len(scope.drivers) - int(observed.get(day, 0))}
                         for day in scope.dates])


def daily_activity_report(scope):
    """Separate distinct daily drivers from inspection volume, including zero days."""
    frame = daily_participation(scope).rename(columns={
        'Recorded': 'drivers_with_PTI', 'No record': 'drivers_without_record'})
    accepted = recorded_inspections(scope.records)
    accepted = accepted[accepted.author_id.isin(scope.drivers.driver_id)]
    volume = accepted.groupby('inspection_date').size()
    frame['PTI_records'] = frame.date.map(volume).fillna(0).astype(int)
    total = len(scope.drivers)
    frame['share_of_drivers_percent'] = (100 * frame.drivers_with_PTI / total).round(1) if total else 0.0
    return frame


def recording_groups(drivers, days):
    regular = drivers.recorded_days.ge((days + 1) // 2)
    review = drivers.activity.eq('Insufficient information')
    return pd.Series({'Regular': int(regular.sum()),
                      'Intermittent': int((drivers.submissions.gt(0) & ~regular).sum()),
                      'No record': int((drivers.submissions.eq(0) & ~review).sum()),
                      'Needs data review': int(review.sum())}).rename_axis('group').reset_index(name='drivers')


def officer_summary(drivers, days):
    frame = drivers.copy()
    frame['officer_key'] = officer_key(frame)
    frame['safety_officer'] = officer_labels(frame)
    frame['regular'] = frame.recorded_days.ge((days + 1) // 2)
    frame['recorded'] = frame.submissions.gt(0)
    frame['no_record'] = frame.activity.eq('No recorded PTI')
    result = frame.groupby(['officer_key', 'safety_officer'], as_index=False).agg(
        drivers=('driver_id', 'nunique'), recorded=('recorded', 'sum'),
        regular=('regular', 'sum'), no_record=('no_record', 'sum'))
    result['intermittent_or_review'] = result.drivers - result.regular - result.no_record
    result['recording_share_percent'] = (100 * result.recorded / result.drivers).round(1)
    return result


def recency_groups(drivers):
    values = pd.to_numeric(drivers.days_since_last_pti_available_history, errors='coerce')
    labels = pd.Series('No dated history', index=drivers.index)
    labels.loc[values.between(0, 2)] = '0–2 days'
    labels.loc[values.between(3, 6)] = '3–6 days'
    labels.loc[values.between(7, 14)] = '7–14 days'
    labels.loc[values.ge(15)] = '15+ days'
    order = ['0–2 days', '3–6 days', '7–14 days', '15+ days', 'No dated history']
    return labels.value_counts().reindex(order, fill_value=0).rename_axis('last_done').reset_index(name='drivers')


def reported_safety_groups(records, source_rows, driver_ids):
    statuses = {key: set() for key in driver_ids}
    if source_rows:
        for row in source_rows:
            driver_id = str(row.get('driverID'))
            if driver_id in statuses:
                statuses[driver_id].update(value.strip().lower() for value in row.get('safetyStatuses', [])
                                           if isinstance(value, str) and value.strip())
    else:
        for row in records.itertuples(index=False):
            if row.author_id in statuses:
                statuses[row.author_id].add(row.safety_status)
    selected = []
    for values in statuses.values():
        value = ('unsafe' if 'unsafe' in values else 'resolved' if 'resolved' in values
                 else next(iter(sorted(values - {'safe', 'unknown'})), None)
                 or ('safe' if 'safe' in values else 'unknown'))
        selected.append(value.title())
    return pd.Series(selected, dtype='object').value_counts().rename_axis('status').reset_index(name='drivers')
