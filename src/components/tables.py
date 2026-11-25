"""Limit rendered rows and export entire filtered tables."""
from math import ceil

import pandas as pd
import streamlit as st


def pretty(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns=lambda name: name.replace("_", " ").title().replace("Id", "ID")
                        .replace("Dvir", "DVIR").replace("Pti", "PTI"))


def display_frame(frame: pd.DataFrame, *, text_columns: tuple[str, ...] = ()) -> pd.DataFrame:
    """Normalize mixed scalar display columns without changing export values."""
    result = frame.copy()
    for column in text_columns:
        if column in result:
            result[column] = result[column].astype('string')
    for column in result.columns:
        if result[column].dtype != object:
            continue
        kind = pd.api.types.infer_dtype(result[column], skipna=True)
        if kind in ('mixed', 'mixed-integer'):
            result[column] = result[column].astype('string')
    return result


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """Escape text that spreadsheet programs could interpret as formulas."""
    safe = frame.copy()
    for column in safe.select_dtypes(include=["object", "string"]).columns:
        safe[column] = safe[column].map(
            lambda value: "'" + value if isinstance(value, str)
            and value.lstrip().startswith(("=", "+", "-", "@")) else value
        )
    return safe.to_csv(index=False).encode("utf-8")


def table(frame: pd.DataFrame, key: str, size: int = 50, *,
          export: bool = True, sort_columns: tuple[str, ...] = ()) -> pd.Index:
    context = st.session_state.get('context')
    if context is not None:
        from ..equipment import report_vehicle_names
        sources=context.filtered_source_rows
        identity=next((column for column in ('driver_id','author_id') if column in frame),None)
        if identity:
            outside=set(frame[identity].dropna())-set(context.scope.drivers.driver_id)
            if outside:
                sources=sources+[row for row in context.data.source_rows
                                 if row.get('_roster_driver_id') in outside or str(row.get('driverID')) in outside]
        frame = report_vehicle_names(frame, context.data.dvir_records, sources)
    if export:
        st.download_button("Download filtered CSV", csv_bytes(frame), f"{key}.csv", key=f"{key}-csv")
    if frame.empty:
        st.info("No matching records.")
        return frame.index
    if sort_columns:
        left, right = st.columns([2, 1])
        column = left.selectbox("Sort all rows by", sort_columns,
                                format_func=lambda name: pretty(frame[[name]]).columns[0],
                                key=f"{key}-sort")
        descending = right.toggle("Descending", value=True, key=f"{key}-descending")
        frame = frame.sort_values(column, ascending=not descending, kind="stable")
    pages = ceil(len(frame) / size)
    page = st.selectbox(f"Page · {len(frame):,} rows", range(1, pages + 1),
                        key=f"{key}-page") if pages > 1 else 1
    current = frame.iloc[(page - 1) * size:page * size]
    st.dataframe(pretty(current), hide_index=True, width="stretch", key=f"{key}-table")
    return current.index


def display_times(frame: pd.DataFrame, timezone: str) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include=["datetimetz"]).columns:
        result[column] = result[column].dt.tz_convert(timezone).dt.strftime("%Y-%m-%d %H:%M %Z")
    return result
