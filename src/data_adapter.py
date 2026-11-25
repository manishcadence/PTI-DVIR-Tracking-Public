"""Validate webhook envelopes and select configurable source arrays."""
import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class PayloadError(ValueError):
    """A payload cannot safely be used for reporting."""


class Envelope(BaseModel):
    inspections: list[dict[str, Any]]
    drivers: list[dict[str, Any]] = Field(default_factory=list)
    driver_assignments: list[dict[str, Any]] = Field(default_factory=list)
    team_assignments: list[dict[str, Any]] = Field(default_factory=list)
    vehicle_assignments: list[dict[str, Any]] = Field(default_factory=list)
    roster_complete: bool = False
    notices: list[str] = Field(default_factory=list)
    retain_supplied_drivers: bool = False
    source_rows: list[dict[str, Any]] = Field(default_factory=list)


def adapt_grouped(rows: list[dict[str, Any]], roster_complete: bool = False) -> Envelope:
    """Expand driver summaries only where timestamps retain inspection alignment."""
    inspections, drivers, mismatches = [], [], []
    for row in rows:
        driver_id = identifier(row.get("driverID"))
        count = row.get("totalPTI")
        if driver_id is None or type(count) is not int or count < 0:
            raise PayloadError("Grouped rows require driverID and a nonnegative integer totalPTI.")
        for key in ("startTimes", "endTimes", "tripTypes", "safetyStatuses",
                    "vehicleIDs", "vehicleNames", "trailerIDs", "trailerNames", "safetyOfficers", "signedBy"):
            if not isinstance(row.get(key, []), list):
                raise PayloadError(f"Grouped {key} must be a JSON array, without displayed index labels.")
        starts, ends = row.get("startTimes", []), row.get("endTimes", [])
        summary_only = 'startTimes' not in row and 'endTimes' not in row
        if (starts and ends and len(starts) != len(ends)) or (count and not starts and not ends and not summary_only):
            raise PayloadError("Grouped timestamps must retain one ordered entry per totalPTI; "
                               "use null for a missing time. Aggregated unique timestamps are insufficient.")
        available = max(len(starts), len(ends))
        if available != count and not summary_only:
            mismatches.append(driver_id)
        count = available
        officers = row.get("safetyOfficers", [])
        drivers.append({"id": driver_id, "name": row.get("driverName"),
                        "safety_officer_name": officers[0] if len(officers) == 1 else None})

        def uniform(key):
            values = row.get(key, [])
            # These lists may be distinct sets, not arrays aligned with the timestamps.
            return values[0] if values and all(value == values[0] for value in values) else None

        statuses = [value.strip().lower() for value in row.get('safetyStatuses', [])
                    if isinstance(value, str) and value.strip()]
        selected_status = ('unsafe' if 'unsafe' in statuses else 'resolved' if 'resolved' in statuses
                           else next((value for value in statuses if value != 'safe'), None)
                           or ('safe' if statuses else None))

        # Joined vehicle/Cogo metadata may repeat the same authored inspection history.
        identity = {"driverID": driver_id, "startTimes": starts, "endTimes": ends}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        for index in range(count):
            inspections.append({
                "id": f"grouped:{digest}:{index}",
                "type": uniform("tripTypes"),
                "startTime": starts[index] if starts else None,
                "endTime": ends[index] if ends else None,
                "safetyStatus": selected_status,
                "authorSignature": {"signatoryUser": {"id": driver_id, "name": row.get("driverName")}},
                "vehicle": {"id": uniform("vehicleIDs"), "name": uniform("vehicleNames")},
                "trailer": {"id": uniform("trailerIDs"), "name": uniform("trailerNames")},
                "sourceFormat": "groupedDriver", "groupedSource": row,
            })
    envelope = Envelope(
        inspections=inspections, drivers=drivers, roster_complete=roster_complete,
        retain_supplied_drivers=True,
        source_rows=rows,
        notices=["Grouped driver data: counts use paired timestamps and generated inspection IDs. "
                 "Equipment list totals count each supplied vehicle/trailer entry. Equipment-to-date "
                 "mapping is unavailable. Safety uses unsafe, then resolved, then other non-safe values "
                 "before safe. Multiple types/assets/officers may lack per-inspection attribution. Defect details, verified signatures, "
                 "training, teams, and current vehicle assignments are unavailable; zero defect "
                 "counts do not establish that equipment has no defects."],
    )
    if mismatches:
        envelope.notices.append(
            f"Grouped count mismatch: {len(set(mismatches))} drivers have totalPTI values that differ "
            "from their timestamp pair counts. Only supplied timestamp pairs are counted. "
            f"Review driver IDs: {', '.join(sorted(set(mismatches)))}."
        )
    if len(rows) != len({row.get('driverID') for row in rows}):
        envelope.notices.append("Repeated driver IDs are present; this alone does not mean duplicate "
                                "inspections. Different equipment/crew source rows are retained. Dated "
                                "activity counts shared timestamp histories once; equipment-list totals "
                                "retain entries from every source row.")
    return envelope


def identifier(value: object) -> str | None:
    return str(value).strip() or None if type(value) in (str, int) else None


class SourceReport(BaseModel):
    """Version 2 combines separately prepared upstream feeds."""

    schemaVersion: int
    rosterComplete: bool = False
    roster: list[dict[str, Any]]
    dvirs: list[dict[str, Any]]
    driverOfficerAssignments: list[dict[str, Any]]
    vehicleOfficerAssignments: list[dict[str, Any]]
    trainingRecords: list[dict[str, Any]] = Field(default_factory=list)
    teamAssignments: list[dict[str, Any]] = Field(default_factory=list)


def adapt_sources(payload: dict[str, Any]) -> Envelope:
    """Join normalized training rows to the roster using Samsara driver IDs."""
    try:
        report = SourceReport.model_validate(payload)
    except ValidationError:
        raise PayloadError("Version 2 webhook response is missing required source arrays.") from None

    training = {}
    ambiguous = set()
    for row in report.trainingRecords:
        driver_id = identifier(row.get("driver_id"))
        if driver_id is None:
            continue
        status = row.get("training_status")
        if not isinstance(status, str) or status not in {"completed", "incomplete", "not_trained", "unknown"}:
            status = "unknown"
        completed_at = row.get("training_completed_at") if status == "completed" else None
        value = (status, completed_at)
        if driver_id in training and training[driver_id] != value:
            ambiguous.add(driver_id)
        training[driver_id] = value

    drivers = []
    for row in report.roster:
        driver_id = identifier(row.get("id", row.get("driver_id")))
        status, completed_at = ("unknown", None)
        if driver_id not in ambiguous:
            status, completed_at = training.get(driver_id, (status, completed_at))
        drivers.append({**row, "training_status": status, "training_completed_at": completed_at})

    return Envelope(
        inspections=report.dvirs, drivers=drivers,
        driver_assignments=report.driverOfficerAssignments,
        vehicle_assignments=report.vehicleOfficerAssignments,
        team_assignments=report.teamAssignments,
        roster_complete=report.rosterComplete,
    )


def adapt(payload: object, keys: tuple[str, str, str, str] = (
    "inspections", "drivers", "driverAssignments", "teamAssignments"
)) -> Envelope:
    """Accept raw arrays, Samsara envelopes, and enriched wrappers."""
    if isinstance(payload, list):
        payload = {"data": payload}
    if not isinstance(payload, dict):
        raise PayloadError("Expected an inspection array or webhook envelope.")
    pagination = payload.get("pagination")
    if pagination is not None and (
        not isinstance(pagination, dict)
        or pagination.get("hasNextPage", False) is not False
    ):
        raise PayloadError("Webhook pagination is incomplete or invalid. Return all pages from n8n.")
    if "schemaVersion" in payload:
        if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 2:
            raise PayloadError("Unsupported webhook schemaVersion. Expected version 2.")
        return adapt_sources(payload)
    inspections, drivers, assignments, teams = keys
    grouped = payload.get("driverSummaries", payload.get(inspections, payload.get("data")))
    if isinstance(grouped, list) and any(isinstance(row, dict) and (('Tms_ID' in row and 'Samsara_DriverID' in row) or any(key in row for key in ('appended_startTIme','appended_startTime','SamsaraStatus','samsara_driverId'))) for row in grouped):
        from .roster_input import adapt_roster
        return adapt_roster(grouped)
    if "driverID" in payload:
        return adapt_grouped([payload])
    if isinstance(grouped, list) and ("driverSummaries" in payload or any(
        isinstance(row, dict) and "driverID" in row for row in grouped
    )):
        if not all(isinstance(row, dict) and "driverID" in row for row in grouped):
            raise PayloadError("Do not mix grouped driver summaries and individual DVIR records.")
        return adapt_grouped(grouped, payload.get("rosterComplete") is True)
    roster = payload.get(drivers, [])
    try:
        return Envelope.model_validate({
            "inspections": payload.get(inspections, payload.get("data")),
            "drivers": roster,
            "driver_assignments": payload.get(assignments, []),
            "team_assignments": payload.get(teams, []),
            "vehicle_assignments": payload.get("vehicleAssignments", []),
            "roster_complete": isinstance(roster, list) and drivers in payload
            and payload.get("rosterComplete") is True,
        })
    except ValidationError:
        raise PayloadError("Webhook arrays are missing or contain invalid records.") from None
