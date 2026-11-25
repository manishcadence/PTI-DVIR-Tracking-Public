"""Separate a report's as-of time from the inspections it contains."""
from datetime import datetime
from zoneinfo import ZoneInfo


def local_report_reference(payload, timezone, modified_at=None, loaded_at=None):
    tz = ZoneInfo(timezone)
    if isinstance(payload, dict):
        for key in ('reportGeneratedAt', 'generatedAt', 'exportedAt', 'reportDate'):
            value = payload.get(key)
            if not isinstance(value, str):
                continue
            try:
                timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=tz)
            return timestamp.astimezone(tz), f'JSON {key}'
    if modified_at is not None:
        return modified_at.astimezone(tz), 'file saved date (no export timestamp supplied)'
    return (loaded_at or datetime.now(tz)).astimezone(tz), 'upload date (no export timestamp supplied)'
