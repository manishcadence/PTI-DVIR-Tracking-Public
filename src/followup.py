"""Compare verified training and current assignments with recorded PTIs."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .analytics import recorded_inspections, uncertain_pretrips
from .filters import Scope


def training_followup(activity: pd.DataFrame, training: pd.DataFrame, scope: Scope,
                      timezone: str, now: datetime | None = None) -> pd.DataFrame:
    tz = ZoneInfo(timezone)
    now = now or datetime.now(tz)
    first = pd.Timestamp(scope.dates[0], tz=tz)
    result = activity.merge(training, on="driver_id", how="left")
    pti = recorded_inspections(scope.records)
    times = pti.groupby("author_id").inspection_time.max()
    review_times = uncertain_pretrips(scope.records).groupby("author_id").inspection_time.max()
    undated = set(recorded_inspections(scope.undated).author_id.dropna())
    categories, timestamps = [], []
    for row in result.itertuples(index=False):
        state = str(row.training_status).lower()
        completed = row.training_completed_at
        category = "Training status unknown"
        if state == "incomplete":
            category = "Training incomplete"
        elif state == "not_trained":
            category = "Not trained"
        elif state == "completed":
            category = "Trained · Completion date unknown"
            if isinstance(completed, str):
                cutoff = pd.to_datetime(completed, errors="coerce", utc=True, format="ISO8601")
                if len(completed) == 10 and pd.notna(cutoff):
                    next_day = cutoff.date() + timedelta(days=1)
                    cutoff = pd.Timestamp(next_day, tz=tz)
                if pd.notna(cutoff):
                    start = max(first, cutoff)
                    latest = times.get(row.driver_id, pd.NaT)
                    if start >= now:
                        category = "Too early to assess"
                    elif pd.notna(latest) and latest >= start:
                        category = "Trained · PTI recorded since training"
                    elif pd.notna(review_times.get(row.driver_id, pd.NaT)) and review_times[row.driver_id] >= start:
                        category = "Trained · Inspection type needs review"
                    elif row.driver_id in undated:
                        category = "Trained · Undated PTI needs review"
                    else:
                        category = "Trained · No PTI recorded since training"
        categories.append(category)
        timestamps.append(completed)
    result["training_follow_up"] = categories
    result["training_completed_at"] = timestamps
    return result
