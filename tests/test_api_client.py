from unittest.mock import patch

import pytest
import requests

from src.api_client import WebhookError, fetch_report

KEYS = ("inspections", "drivers", "driverAssignments", "teamAssignments")
URL = "https://example.invalid/webhook/secret-path"


@pytest.mark.parametrize("days", [7, 15, 30])
def test_request_period_and_timeout(days):
    with patch("requests.Session.get") as get:
        get.return_value.status_code = 200
        get.return_value.json.return_value = []
        report, timestamp = fetch_report(URL, days, KEYS, token="test-token")
    kwargs = get.call_args.kwargs
    assert kwargs["params"] == {"days": days}
    assert kwargs["timeout"] == (5, 15)
    assert not kwargs["allow_redirects"]
    assert report.inspections == [] and timestamp.tzinfo is not None


def test_timeout_redacts_url():
    with patch("requests.Session.get", side_effect=requests.Timeout(URL)):
        with pytest.raises(WebhookError, match="Could not reach n8n") as error:
            fetch_report(URL, 7, KEYS)
    assert "secret-path" not in str(error.value)


def test_empty_body():
    with patch("requests.Session.get") as get:
        get.return_value.status_code = 200
        get.return_value.json.side_effect = requests.exceptions.JSONDecodeError("empty", "", 0)
        with pytest.raises(WebhookError, match="invalid or empty JSON"):
            fetch_report(URL, 15, KEYS)


def test_snapshot_isolated_by_source_and_period(tmp_path, dvir):
    from datetime import datetime, timezone

    from src.data_adapter import adapt
    from src.storage import latest_snapshot, save_snapshot

    path = str(tmp_path / "snapshots.sqlite")
    synced = datetime.now(timezone.utc)
    report = adapt([dvir])
    save_snapshot(path, "first", 7, synced, report)
    save_snapshot(path, "first", 7, synced, report)
    assert latest_snapshot(path, "first", 7) == (report, synced)
    assert latest_snapshot(path, "first", 15) is None
    assert latest_snapshot(path, "second", 7) is None
