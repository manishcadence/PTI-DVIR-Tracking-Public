from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.report_dates import local_report_reference


def test_export_time_is_authoritative_over_file_and_inspection_dates():
    payload = {'reportGeneratedAt': '2026-11-17T14:41:16.466-06:00',
               'driverSummaries': [{'startTimes': ['2026-11-16T12:00:00Z']}]}
    reference, basis = local_report_reference(payload, 'America/Chicago',
                    modified_at=datetime(2026, 11, 18, tzinfo=ZoneInfo('America/Chicago')))
    assert reference.date() == date(2026, 11, 17)
    assert reference.hour == 14
    assert basis == 'JSON reportGeneratedAt'


def test_raw_array_uses_file_date_and_upload_uses_loaded_date():
    stamp = datetime(2026, 11, 17, 14, 44, tzinfo=ZoneInfo('America/Chicago'))
    reference, basis = local_report_reference([], 'America/Chicago', modified_at=stamp)
    assert reference.date() == date(2026, 11, 17) and basis.startswith('file saved date')
    reference, basis = local_report_reference([], 'America/Chicago', loaded_at=stamp)
    assert reference == stamp and basis.startswith('upload date')


def test_export_utc_offset_and_invalid_metadata_fallback():
    stamp = datetime(2026, 11, 17, tzinfo=ZoneInfo('America/Chicago'))
    reference, _ = local_report_reference({'exportedAt': '2026-11-17T05:00:00Z'},
                                         'America/Chicago', modified_at=stamp)
    assert reference.date() == date(2026, 11, 16)
    reference, basis = local_report_reference({'generatedAt': 'bad'}, 'America/Chicago', modified_at=stamp)
    assert reference == stamp and basis.startswith('file saved date')
