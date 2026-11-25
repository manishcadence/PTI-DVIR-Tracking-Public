"""Last-seen dates from full available history, separate from board totals."""
import pandas as pd

from .analytics import recorded_inspections, uncertain_pretrips


def history_summary(data, report_end):
    records = data.dvir_records
    records = records[records.inspection_time.notna() & records.inspection_date.le(report_end)]
    ids = pd.concat([data.drivers.driver_id, data.dvir_records.author_id], ignore_index=True)
    result = pd.DataFrame({'driver_id': ids.dropna().drop_duplicates()})
    for column, source in (
        ('last_pti_available_history', recorded_inspections(records)),
        ('last_inspection_available_history', records),
        ('last_mixed_type_inspection', uncertain_pretrips(records)),
    ):
        last = source.groupby('author_id').inspection_date.max()
        result[column] = result.driver_id.map(last)
    result['days_since_last_pti_available_history'] = (
        pd.Timestamp(report_end) - pd.to_datetime(result.last_pti_available_history)
    ).dt.days.astype('Int64')
    return result
