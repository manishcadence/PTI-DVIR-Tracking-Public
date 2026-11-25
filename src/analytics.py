"""Recorded activity metrics without expected-inspection assumptions."""
import pandas as pd

from .filters import Scope, officer_key, officer_labels
from .normalization import FleetData


def pretrips(records: pd.DataFrame) -> pd.DataFrame:
    return records.loc[records.inspection_type.eq("preTrip")]


def recorded_inspections(records: pd.DataFrame) -> pd.DataFrame:
    """Both pre-trip and post-trip inspections count as done, including grouped mixtures."""
    def supported_group(raw):
        if not isinstance(raw, dict) or raw.get('sourceFormat') != 'groupedDriver':
            return False
        if raw.get('groupedSource', {}).get('_activity_type_unspecified'):
            return True  # Dated DVIR aggregate supplied without a trip-type column.
        types = raw.get('groupedSource', {}).get('tripTypes', [])
        return bool(types) and all(value in ('preTrip', 'postTrip') for value in types)
    return records.loc[records.inspection_type.isin(['preTrip', 'postTrip']) |
                       records.raw.map(supported_group).astype(bool)]


def uncertain_pretrips(records: pd.DataFrame) -> pd.DataFrame:
    """Review grouped rows that mix supported trip types with other unknown types."""
    def uncertain(raw):
        if not isinstance(raw, dict) or raw.get("sourceFormat") != "groupedDriver":
            return False
        types = raw.get("groupedSource", {}).get("tripTypes", [])
        return any(value in ('preTrip', 'postTrip') for value in types) and any(
            value not in ('preTrip', 'postTrip') for value in types)
    return records.loc[records.raw.map(uncertain).astype(bool)]


def driver_activity(scope: Scope) -> pd.DataFrame:
    """Aggregate author credit only, retaining drivers with zero dated PTIs."""
    pti = recorded_inspections(scope.records).copy()
    pti["unsafe"] = pti.safety_status.eq("unsafe")
    summary = pti.groupby("author_id").agg(
        submissions=("dvir_id", "size"),
        recorded_days=("inspection_date", "nunique"),
        last_pti=("inspection_date", "max"),
        vehicles=("vehicle_id", "nunique"),
        unsafe=("unsafe", "sum"),
        unresolved=("unresolved_defects", "sum"),
    )
    output = scope.drivers.merge(summary, left_on="driver_id", right_index=True, how="left")
    counts = ["submissions", "recorded_days", "vehicles", "unsafe", "unresolved"]
    output[counts] = output[counts].fillna(0).astype(int)
    review = uncertain_pretrips(scope.records)
    output["inspection_type_review"] = output.driver_id.map(review.groupby("author_id").size()).fillna(0).astype(int)
    output["days_without_pti"] = len(scope.dates) - output.recorded_days
    output["days_since_last_pti"] = (
        pd.Timestamp(scope.dates[-1]) - pd.to_datetime(output.last_pti)
    ).dt.days.astype("Int64")
    teams = scope.records[scope.records.team_confirmed.astype(bool)]
    output["co_driver"] = output.driver_id.isin(teams.author_id) | output.driver_id.isin(teams.co_driver_id)
    output["activity"] = "No recorded PTI"
    output.loc[output.driver_id.isin(recorded_inspections(scope.undated).author_id)
               & output.submissions.eq(0), "activity"] = "Insufficient information"
    review_ids = set(review.author_id) | set(uncertain_pretrips(scope.undated).author_id)
    output.loc[output.driver_id.isin(review_ids) & output.submissions.eq(0), "activity"] = "Insufficient information"
    output.loc[output.submissions.gt(0), "activity"] = "Intermittent submitter"
    output.loc[output.recorded_days.ge((len(scope.dates) + 1) // 2), "activity"] = "Frequent submitter"
    return output.sort_values(["submissions", "driver_id"], ascending=[False, True])


def daily_status(scope: Scope, driver_ids: list[str]) -> pd.DataFrame:
    """Return date cells with unsafe taking precedence over incomplete and recorded."""
    pti = recorded_inspections(scope.records)
    pti = pti[pti.author_id.isin(driver_ids)].copy()
    pti["status"] = 1
    pti.loc[pti.ambiguous.astype(bool), "status"] = 2
    pti.loc[pti.safety_status.eq("unsafe"), "status"] = 3
    review = uncertain_pretrips(scope.records)
    review = review[review.author_id.isin(driver_ids)].assign(status=2)
    cells = pd.concat([pti, review]).pivot_table(index="author_id", columns="inspection_date", values="status", aggfunc="max")
    return cells.reindex(index=driver_ids, columns=scope.dates).fillna(0).astype(int)


def shared_vehicles(records: pd.DataFrame) -> pd.DataFrame:
    """Identify shared vehicles by ID, without inferring team assignment."""
    rows = records.dropna(subset=["vehicle_id", "author_id"])
    counts = rows.groupby("vehicle_id").agg(
        vehicle_name=("vehicle_name", "last"), distinct_authors=("author_id", "nunique")
    )
    return counts[counts.distinct_authors.gt(1)].reset_index().sort_values(
        "distinct_authors", ascending=False
    )


def calculate_expected_ptis(driver_id, driving_events=None, company_policy=None) -> None:
    """Future integration point for driving events and company inspection policy."""
    return None


def confirmed_team_records(records: pd.DataFrame, data: FleetData, officer: str = "") -> pd.DataFrame:
    """Join team evidence and match an officer assigned to either participant."""

    teams = records[records.team_confirmed.astype(bool)].merge(
        data.team_assignments[["dvir_id", "source"]], on="dvir_id", how="left"
    )
    assignments = data.driver_assignments.set_index("driver_id")
    partner = pd.DataFrame({
        column: teams.co_driver_id.map(assignments[column])
        for column in ("officer_id", "officer_name")
    })
    teams["author_officer"] = officer_labels(teams)
    teams["co_driver_officer"] = officer_labels(partner)
    if officer:
        teams = teams[officer_key(teams).eq(officer)
                      | (teams.co_driver_id.notna() & officer_key(partner).eq(officer))]
    return teams
