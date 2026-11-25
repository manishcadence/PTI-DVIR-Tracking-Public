from src.diagnostics import log_report_diagnostics, report_logger


def test_diagnostics_are_saved_once_to_local_log(tmp_path):
    path = tmp_path / 'logs' / 'dashboard.log'
    notices = ['Grouped count mismatch: test', 'Repeated driver IDs: test']
    log_report_diagnostics(notices, path)
    log_report_diagnostics(notices, path)
    for handler in report_logger(str(path)).handlers:
        handler.flush()
    text = path.read_text(encoding='utf-8')
    assert text.count(notices[0]) == 1
    assert text.count(notices[1]) == 1
