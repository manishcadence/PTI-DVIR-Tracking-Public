from unittest.mock import patch

from src.ui import local_report_signature, watch_local_report


def test_file_poll_requests_full_reload_only_when_signature_changes(tmp_path):
    path = tmp_path / 'report.json'
    path.write_text('[]', encoding='utf-8')
    loaded = local_report_signature(path)
    with patch('src.ui.st.rerun') as rerun:
        watch_local_report.__wrapped__(str(path), loaded)
        rerun.assert_not_called()
        path.write_text('{"data": []}', encoding='utf-8')
        watch_local_report.__wrapped__(str(path), loaded)
        rerun.assert_called_once_with(scope='app')
        path.unlink()
        watch_local_report.__wrapped__(str(path), loaded)
        assert rerun.call_count == 1
