"""Reusable full-population CSV download, independent of visible UI subsets."""
import streamlit as st

from ..rating_report import build_rating_report
from .tables import csv_bytes


@st.cache_data(show_spinner=False, max_entries=8)
def cached_rating_report(data, dates, timezone):
    return build_rating_report(data, dates, timezone)


def rating_download(context, key):
    report = cached_rating_report(context.data, context.scope.dates, context.timezone)
    st.download_button('Download all-driver rating CSV', b'\xef\xbb\xbf' + csv_bytes(report),
                       file_name=f'driver-rating-inputs-{len(context.scope.dates)}d-{context.scope.dates[-1]}.csv',
                       mime='text/csv', key=f'{key}-all-driver-rating-csv', icon=':material/download:')
    return report
