"""Normalize DVIR records and their ID-based relationships."""
from dataclasses import dataclass, field

import pandas as pd

from .data_adapter import Envelope, identifier


@dataclass
class FleetData:
    drivers: pd.DataFrame
    driver_assignments: pd.DataFrame
    dvir_records: pd.DataFrame
    dvir_signatures: pd.DataFrame
    dvir_defects: pd.DataFrame
    team_assignments: pd.DataFrame
    roster_complete: bool
    missing_ids: int
    training: pd.DataFrame
    vehicle_assignments: pd.DataFrame
    retain_supplied_drivers: bool = False
    source_rows: list[dict] = field(default_factory=list)


def obj(value):
    return value if isinstance(value, dict) else {}


def items(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def label(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def utc(values: pd.Series) -> pd.Series:
    """Accept timestamp strings, with naive timestamps interpreted as UTC."""
    return pd.to_datetime(
        values.map(lambda value: value if isinstance(value, str) else None),
        utc=True, errors="coerce", format="mixed",
    )


RECORD = """dvir_id inspection_type start_time end_time author_id author_name vehicle_id
vehicle_name trailer_id trailer_name officer_id officer_name co_driver_id co_driver_name
safety_status vehicle_defects trailer_defects total_defects resolved_defects unresolved_defects
team_confirmed raw""".split()
DEFECT = """dvir_id asset_type asset_id asset_name defect_type description reported_time
resolution_status resolved_time mechanic_notes""".split()
SIGNATURE = "dvir_id role user_id user_name signed_time signature_type".split()
ASSIGNMENT = "driver_id officer_id officer_name".split()
TEAM = "dvir_id driver_id co_driver_id co_driver_name vehicle_id source".split()


def normalize(envelope: Envelope, timezone: str) -> FleetData:
    """Preserve raw DVIRs and materialize stable schemas even for empty feeds."""
    roster = {}
    officers = {}
    for entry in envelope.drivers:
        driver_id = identifier(entry.get("id", entry.get("driver_id")))
        if driver_id:
            roster[driver_id] = label(entry.get("name"))
            officers[driver_id] = (
                identifier(entry.get("safety_officer_id")), label(entry.get("safety_officer_name"))
            )
    for entry in envelope.driver_assignments:
        driver_id = identifier(entry.get("driver_id"))
        if driver_id and entry.get("current", True) is True and not entry.get("endTime"):
            officers[driver_id] = (
                identifier(entry.get("safety_officer_id")), label(entry.get("safety_officer_name"))
            )

    team_by_dvir = {}
    for entry in envelope.team_assignments:
        dvir_id = identifier(entry.get("dvir_id"))
        driver_id = identifier(entry.get("driver_id"))
        co_id = identifier(entry.get("co_driver_id"))
        if dvir_id and driver_id and co_id and co_id != driver_id:
            team_by_dvir.setdefault((dvir_id, driver_id), {})[co_id] = label(entry.get("co_driver_name"))

    seen = set()
    records, signatures, defects, teams = [], [], [], []
    missing_ids = 0
    for entry in envelope.inspections:
        dvir_id = identifier(entry.get("id"))
        if not dvir_id:
            missing_ids += 1
            continue
        if dvir_id in seen:
            continue
        seen.add(dvir_id)
        author = obj(obj(entry.get("authorSignature")).get("signatoryUser"))
        author_id = identifier(author.get("id"))
        author_name = label(author.get("name"))
        explicit_id = identifier(entry.get("co_driver_id"))
        explicit_name = label(entry.get("co_driver_name"))
        candidates = team_by_dvir.get((dvir_id, author_id), {})
        mapped_id = next(iter(candidates)) if len(candidates) == 1 else None
        co_id = explicit_id if explicit_id != author_id else None
        co_name = explicit_name if explicit_id is None or explicit_id != author_id else None
        if co_id is None and mapped_id is not None:
            co_id = mapped_id
            co_name = candidates[mapped_id] or roster.get(mapped_id)
        if co_id:
            co_name = co_name or candidates.get(co_id) or roster.get(co_id)
        assets = {kind: obj(entry.get(kind)) for kind in ("vehicle", "trailer")}
        officer_id, officer_name = officers.get(author_id, (None, None))
        record = {
            "dvir_id": dvir_id, "inspection_type": label(entry.get("type")),
            "start_time": entry.get("startTime"), "end_time": entry.get("endTime"),
            "author_id": author_id, "author_name": author_name or roster.get(author_id),
            "co_driver_id": co_id, "co_driver_name": co_name,
            "team_confirmed": bool(co_id or co_name),
            "officer_id": officer_id or identifier(entry.get("safety_officer_id")),
            "officer_name": officer_name if officer_id or officer_name else label(entry.get("safety_officer_name")),
            "safety_status": (label(entry.get("safetyStatus")) or "unknown").lower(),
            "raw": entry,
        }
        if record["team_confirmed"]:
            teams.append((dvir_id, author_id, co_id, co_name, identifier(assets["vehicle"].get("id")),
                          "DVIR enrichment" if explicit_id or explicit_name else "Team assignment"))
        for role in ("authorSignature", "secondSignature", "thirdSignature"):
            signature = obj(entry.get(role))
            if signature and entry.get("sourceFormat") != "groupedDriver":
                user = obj(signature.get("signatoryUser"))
                signatures.append((dvir_id, role, identifier(user.get("id")), label(user.get("name")),
                                   signature.get("signedAtTime"), label(signature.get("type"))))
        for signature in items(entry.get("additionalSignatures")):
            user = obj(signature.get("signatoryUser"))
            signatures.append((dvir_id, "additionalSignatures", identifier(user.get("id")),
                               label(user.get("name")), signature.get("signedAtTime"),
                               label(signature.get("type"))))
        resolved = 0
        for kind, asset in assets.items():
            asset_id = identifier(asset.get("id"))
            asset_name = label(asset.get("name"))
            asset_defects = items(entry.get(f"{kind}Defects"))
            record.update({f"{kind}_id": asset_id, f"{kind}_name": asset_name,
                           f"{kind}_defects": len(asset_defects)})
            for defect in asset_defects:
                resolution = obj(defect.get("resolution"))
                resolved_time = defect.get("resolvedAtTime") or resolution.get("resolvedAtTime")
                status = (label(defect.get("status") or resolution.get("status")) or "").lower()
                has_resolution_time = isinstance(resolved_time, str) and pd.notna(
                    pd.to_datetime(resolved_time, utc=True, errors="coerce")
                )
                is_resolved = status == "resolved" or (
                    status not in {"unresolved", "open", "pending"}
                    and (defect.get("isResolved") is True or has_resolution_time)
                )
                resolved += is_resolved
                defects.append((dvir_id, kind, asset_id, asset_name,
                                label(defect.get("defectType") or defect.get("type")) or "Unknown",
                                label(defect.get("description") or defect.get("comment")),
                                defect.get("reportedAtTime") or entry.get("startTime"),
                                "Resolved" if is_resolved else "Unresolved", resolved_time,
                                label(defect.get("mechanicNotes") or resolution.get("mechanicNotes")
                                      or entry.get("mechanicNotes"))))
        record["total_defects"] = record["vehicle_defects"] + record["trailer_defects"]
        record["resolved_defects"] = resolved
        record["unresolved_defects"] = record["total_defects"] - resolved
        records.append(record)

    dvirs = pd.DataFrame(records, columns=RECORD)
    signature_table = pd.DataFrame(signatures, columns=SIGNATURE)
    defect_table = pd.DataFrame(defects, columns=DEFECT)
    for frame, columns in (
        (dvirs, ("start_time", "end_time")), (signature_table, ("signed_time",)),
        (defect_table, ("reported_time", "resolved_time")),
    ):
        for column in columns:
            frame[column] = utc(frame[column])
    dvirs["inspection_time"] = dvirs.start_time.fillna(dvirs.end_time)
    local = dvirs.inspection_time.dt.tz_convert(timezone)
    dvirs["inspection_date"] = local.dt.date
    dvirs["ambiguous"] = (
        dvirs.start_time.isna() | (dvirs.end_time < dvirs.start_time)
        | ~dvirs.safety_status.isin(["safe", "unsafe", "resolved"])
    )
    driver_table = pd.DataFrame(
        [(driver_id, name) for driver_id, name in roster.items()],
        columns=["driver_id", "driver_name"],
    )
    training = pd.DataFrame([
        (identifier(row.get("id", row.get("driver_id"))), label(row.get("training_status")),
         label(row.get("training_completed_at"))) for row in envelope.drivers
    ], columns=["driver_id", "training_status", "training_completed_at"])
    training = training.dropna(subset=["driver_id"]).drop_duplicates("driver_id", keep="last")
    vehicle_assignments = pd.DataFrame([
        (identifier(row.get("vehicle_id")), label(row.get("vehicle_name")),
         identifier(row.get("safety_officer_id")), label(row.get("safety_officer_name")))
        for row in envelope.vehicle_assignments
    ], columns=["vehicle_id", "vehicle_name", "officer_id", "officer_name"])
    vehicle_assignments = vehicle_assignments.dropna(subset=["vehicle_id"]).drop_duplicates()
    return FleetData(
        driver_table, pd.DataFrame([(key, *value) for key, value in officers.items()], columns=ASSIGNMENT),
        dvirs, signature_table, defect_table, pd.DataFrame(teams, columns=TEAM),
        envelope.roster_complete, missing_ids, training, vehicle_assignments,
        retain_supplied_drivers=envelope.retain_supplied_drivers,
        source_rows=envelope.source_rows,
    )
