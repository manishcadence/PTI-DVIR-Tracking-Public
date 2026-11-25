"""Reusable dashboard metric cards."""
import streamlit as st


def metrics(values: list[tuple[str, int]]) -> None:
    for offset in range(0, len(values), 4):
        row = values[offset:offset + 4]
        for column, (label, value) in zip(st.columns(len(row)), row):
            column.metric(label, f"{value:,}", border=True)
