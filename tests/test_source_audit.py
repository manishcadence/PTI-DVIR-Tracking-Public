from src.source_audit import duplicate_drivers


def test_duplicate_ids_show_source_rows_and_differences():
    rows = [{'driverID': 'D1', 'driverName': 'Alex', 'startTimes': ['a'], 'endTimes': ['b'],
             'trailerIDs': ['T1']},
            {'driverID': 'D2', 'driverName': 'Jordan'},
            {'driverID': 'D1', 'driverName': 'Alex', 'startTimes': ['a'], 'endTimes': ['b'],
             'trailerIDs': ['T2']}]
    report = duplicate_drivers(rows)
    assert len(report) == 1
    row = report.iloc[0]
    assert row.driver_id == 'D1' and row.source_rows == 2
    assert row.source_row_numbers == '1, 3'
    assert row.distinct_timestamp_histories == 1
    assert row.differing_fields == 'trailerIDs'


def test_empty_audit_has_stable_columns():
    assert duplicate_drivers([]).empty
    assert 'source_row_numbers' in duplicate_drivers([]).columns
