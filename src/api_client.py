"""Read and validate n8n reports with bounded retries and redacted errors."""
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .data_adapter import Envelope, PayloadError, adapt


class WebhookError(RuntimeError):
    """A safe, user-facing webhook failure."""


def fetch_report(url: str, days: int, keys: tuple[str, str, str, str], token: str = "",
                 timeout: float = 15) -> tuple[Envelope, datetime]:
    if days not in (7, 15, 30):
        raise ValueError("Fetch period must be 7, 15 or 30 days.")
    if not url.startswith(("https://", "http://")):
        raise WebhookError("Configure a valid HTTP(S) n8n webhook URL.")
    try:
        with requests.Session() as session:
            retries = Retry(total=2, backoff_factor=0.5, allowed_methods={"GET"},
                            status_forcelist=[429, 500, 502, 503, 504],
                            raise_on_status=False, respect_retry_after_header=False)
            for scheme in ("https://", "http://"):
                session.mount(scheme, HTTPAdapter(max_retries=retries))
            headers = {"Accept": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = session.get(url, params={"days": days}, headers=headers,
                                   timeout=(min(timeout, 5), timeout), allow_redirects=False)
            if response.status_code != 200:
                raise WebhookError(f"n8n returned HTTP {response.status_code}. Check the workflow and authentication.")
            envelope = adapt(response.json(), keys)
    except requests.exceptions.JSONDecodeError:
        raise WebhookError("n8n returned invalid or empty JSON.") from None
    except requests.RequestException:
        raise WebhookError("Could not reach n8n. Check connectivity and retry with Refresh.") from None
    except PayloadError as error:
        raise WebhookError(str(error)) from None
    return envelope, datetime.now(timezone.utc)
