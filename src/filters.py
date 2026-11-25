"""Build a consistent reporting scope for every dashboard page."""
from dataclasses import dataclass
from datetime import date, timedelta
import json

import pandas as pd

from .normalization import FleetData


@dataclass(frozen=True)
class Filters:
    officer: str = ""
    driver: str = ""
    vehicle: str = ""
    trailer: str = ""
    co_driver: str = ""


@dataclass
class Scope:
    dates: list[date]
    drivers: pd.DataFrame
    records: pd.DataFrame
    undated: pd.DataFrame


def reporting_dates(days: int, today: date) -> list[date]:
    """Include today and the preceding local calendar days."""
    if days not in (7, 15):
        raise ValueError("Reporting period must be 7 or 15 days.")
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def search(frame: pd.DataFrame, columns: list[str], query: str) -> pd.Series:
    query = query.strip()
    mask = pd.Series(not query, index=frame.index, dtype=bool)
    for column in columns:
        mask |= frame[column].fillna("").astype(str).str.contains(query, case=False, regex=False)
    return mask


def _officer_values(values: pd.Series) -> pd.Series:
    text = values.fillna('').astype(str).str.strip()
    return text.mask(text.str.casefold().isin({'', 'unknown', 'unassigned', 'none', 'null', 'nan'}))


def officer_key(frame: pd.DataFrame) -> pd.Series:
    return ('id:' + _officer_values(frame.officer_id)).fillna(
        ('name:' + _officer_values(frame.officer_name)).fillna('unknown'))


def officer_labels(frame: pd.DataFrame) -> pd.Series:
    """Missing assignment is a visible category, never a reason to drop activity."""
    return _officer_values(frame.officer_name).fillna(_officer_values(frame.officer_id)).fillna('Unassigned')


def source_assets_match(row: dict, filters: Filters) -> bool:
    """Literal ID/name search over full grouped asset arrays and joined vehicle fields."""
    for kind, query in (('vehicle', filters.vehicle), ('trailer', filters.trailer)):
        query = query.strip().casefold()
        if not query:
            continue
        values = [*(row.get(f'{kind}IDs') or []), *(row.get(f'{kind}Names') or []),
                  row.get(f'{kind}Name'), row.get(f'samsara{kind.title()}id')]
        if not any(query in str(value).casefold() for value in values if value is not None):
            return False
    return True


def history_key(row: dict) -> str:
    return json.dumps([str(row.get('driverID')), row.get('startTimes') or [], row.get('endTimes') or []])


def driver_population(data: FleetData, records: pd.DataFrame) -> pd.DataFrame:
    """Combine roster and observed authors, using the latest available enrichment."""
    observed = (
        records.dropna(subset=["author_id"])
        .sort_values("inspection_time", na_position="first")
        .drop_duplicates("author_id", keep="last")
        .rename(columns={"author_id": "driver_id", "author_name": "driver_name"})
    )
    names = data.drivers if data.roster_complete or data.retain_supplied_drivers else data.drivers[
        data.drivers.driver_id.isin(observed.driver_id)
    ]
    drivers = names.merge(observed[["driver_id", "driver_name"]], how="outer", on="driver_id",
                          suffixes=("", "_observed"))
    drivers["driver_name"] = drivers.pop("driver_name").fillna(drivers.pop("driver_name_observed"))
    if any('_roster_driver_id' in row for row in data.source_rows):
        drivers = drivers[drivers.driver_id.isin(data.drivers.driver_id)]
    drivers = drivers.merge(data.driver_assignments, on="driver_id", how="left")
    fallback = observed.set_index("driver_id")
    missing_officer = drivers.officer_id.isna() & drivers.officer_name.isna()
    for column in ("officer_id", "officer_name"):
        drivers.loc[missing_officer, column] = drivers.loc[missing_officer, "driver_id"].map(fallback[column])
    return drivers


def apply_filters(data: FleetData, dates: list[date], filters: Filters) -> Scope:
    """Keep zero-submission drivers unless a record-level filter is active."""
    source = data.dvir_records
    dated = source[source.inspection_date.isin(dates)]
    undated = source[source.inspection_time.isna()]
    drivers = driver_population(data, dated)
    drivers = drivers[
        search(drivers, ["driver_id", "driver_name"], filters.driver)
        & (officer_key(drivers).eq(filters.officer) if filters.officer else True)
    ]
    matching_histories = {history_key(row) for row in data.source_rows
                          if source_assets_match(row, filters)}

    def select(frame: pd.DataFrame) -> pd.DataFrame:
        author_matches = frame.author_id.isin(drivers.driver_id)
        if not filters.officer and not filters.driver.strip():
            author_matches |= True
        assets = (search(frame, ["vehicle_id", "vehicle_name"], filters.vehicle)
                  & search(frame, ["trailer_id", "trailer_name"], filters.trailer))
        if filters.vehicle.strip() or filters.trailer.strip():
            def grouped_match(raw):
                if not isinstance(raw, dict) or raw.get('sourceFormat') != 'groupedDriver':
                    return False
                row = raw.get('groupedSource', {})
                return source_assets_match(row, filters) or history_key(row) in matching_histories
            assets |= frame.raw.map(grouped_match).astype(bool)
        return frame[
            author_matches
            & assets
            & (frame.co_driver_id.eq(filters.co_driver) if filters.co_driver else True)
        ]

    records = select(dated)
    unknown = select(undated)
    if filters.vehicle.strip() or filters.trailer.strip() or filters.co_driver:
        source_ids = {str(row.get('_roster_driver_id') or row.get('driverID')) for row in data.source_rows
                      if (row.get('_roster_driver_id') or ('startTimes' not in row and 'endTimes' not in row))
                      and source_assets_match(row, filters)} if not filters.co_driver else set()
        drivers = drivers[drivers.driver_id.isin(set(records.author_id) | source_ids)]
    records = records.merge(drivers[["driver_id", "officer_id", "officer_name"]],
                            left_on="author_id", right_on="driver_id", how="left",
                            suffixes=("", "_current"))
    known = records.officer_id_current.notna() | records.officer_name_current.notna()
    for name in ("officer_id", "officer_name"):
        records.loc[known, name] = records.loc[known, f"{name}_current"]
    return Scope(dates, drivers, records.drop(columns=["driver_id", "officer_id_current", "officer_name_current"]), unknown)
