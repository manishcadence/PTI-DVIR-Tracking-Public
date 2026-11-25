"""Shared Plotly styling and chart rendering."""
import pandas as pd
import plotly.express as px
import streamlit as st

BLUE = "#265f99"
GREEN = "#21845e"
YELLOW = "#d9a229"
RED = "#bc354c"
GRAY = "#dce3eb"


def show(fig, key: str, height: int = 290) -> None:
    fig.update_layout(margin=dict(l=6, r=12, t=10, b=12),
                      font=dict(family="Inter, sans-serif"), height=height)
    st.plotly_chart(fig, key=key, width="stretch", config={"displaylogo": False})


def chart(title: str, frame: pd.DataFrame, x: str, y: str, *,
          line: bool = False, color: str | None = None,
          colors: dict[str, str] | None = None, horizontal: bool = False) -> None:
    st.markdown(f"**{title}**")
    if frame.empty:
        st.caption("No matching data.")
        return
    labels = {column: column.replace("_", " ").capitalize() for column in frame.columns}
    options = dict(x=x, y=y, labels=labels, color=color, color_discrete_map=colors or {},
                   color_discrete_sequence=[BLUE, GREEN, YELLOW, RED, GRAY])
    figure = px.line(frame, markers=True, **options) if line else px.bar(
        frame, orientation="h" if horizontal else "v", **options
    )
    if horizontal:
        figure.update_yaxes(autorange="reversed")
    figure.update_yaxes(rangemode="tozero")
    show(figure, title)


def daily_trend(records: pd.DataFrame, dates: list) -> pd.DataFrame:
    return (records.groupby("inspection_date").size().reindex(dates, fill_value=0)
            .rename_axis("date").reset_index(name="submissions"))


def counts(values: pd.Series, name: str) -> pd.DataFrame:
    return values.value_counts().rename_axis(name).reset_index(name="records")


def asset_labels(frame: pd.DataFrame, name: str, asset_id: str) -> pd.Series:
    names = frame[name].fillna("Unknown").astype(str)
    ids = frame[asset_id]
    return names.where(ids.isna(), names + " (" + ids.fillna("").astype(str) + ")")
