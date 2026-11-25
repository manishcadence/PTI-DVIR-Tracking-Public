"""Compact date-filtered daily driver table."""
from datetime import date
from math import ceil

import pandas as pd
import streamlit as st

from ..analytics import daily_status, recorded_inspections
from .tables import csv_bytes


STATUS = {
    0: ('No record', '#64748b', '#f1f5f9'),
    1: ('Done', '#167449', '#eaf7ef'),
    2: ('Needs review', '#956000', '#fff7df'),
    3: ('Unsafe', '#b42332', '#fff0f1'),
}


def select_day(value):
    st.session_state['daily-board-date'] = value


def daily_driver_rows(scope, view, selected_day):
    marks = daily_status(scope, view.driver_id.tolist())
    rows = view.copy()
    rows['daily_status'] = rows.driver_id.map(marks[selected_day]).fillna(0).astype(int)
    records = recorded_inspections(scope.records)
    counts = records[records.inspection_date.eq(selected_day)].groupby('author_id').dvir_id.nunique()
    rows['inspections_on_date'] = rows.driver_id.map(counts).fillna(0).astype(int)
    rows['daily_mark'] = rows.daily_status.map(lambda value: STATUS[value][0])
    return rows, marks


def render_daily_drivers(scope, view, timezone):
    st.subheader('Daily driver board', anchor='daily-driver-board')
    latest = scope.dates[-1]
    allowed = [day.isoformat() for day in reversed(scope.dates)]
    if st.session_state.get('daily-board-date') not in allowed:
        st.session_state['daily-board-date'] = latest.isoformat()
    accepted = recorded_inspections(scope.records)
    accepted = accepted[accepted.author_id.isin(view.driver_id)]
    counts_by_date = accepted.groupby('inspection_date').author_id.nunique()
    day_column, today_column = st.columns([5, 1], vertical_alignment='bottom')
    selected_value = day_column.selectbox(
        'Report date', allowed, key='daily-board-date',
        format_func=lambda value: ('Latest data · ' if value == latest.isoformat() else '')
            + date.fromisoformat(value).strftime('%a, %d %b')
            + f' · {int(counts_by_date.get(date.fromisoformat(value), 0)):,} recorded')
    today_column.button('Today', key='daily-today', width='stretch',
                        help=f'Latest inspection date in the JSON: {latest:%b %d, %Y}',
                        on_click=select_day, args=(latest.isoformat(),))
    selected = date.fromisoformat(selected_value)
    st.caption(f'Latest inspection date: {latest:%b %d, %Y}. The list follows inspection dates, not the export time.')
    rows, _ = daily_driver_rows(scope, view, selected)
    total = len(rows)
    recorded = int(rows.inspections_on_date.gt(0).sum())
    for column, (label, count) in zip(st.columns(4), [
        ('Recorded', recorded), ('No record', int(rows.daily_status.eq(0).sum())),
        ('Needs review', int(rows.daily_status.eq(2).sum())), ('Unsafe', int(rows.daily_status.eq(3).sum()))
    ]):
        column.metric(label, f'{count:,}', border=True)
    st.progress(recorded / total if total else 0,
                text=f'{recorded:,} of {total:,} drivers recorded an inspection on this date')
    if not recorded and not accepted.empty:
        latest_activity = accepted.inspection_date.max()
        st.caption(f'No inspections on {selected:%b %d}. The latest date with recorded activity is {latest_activity:%b %d}.')
    selected_status = st.segmented_control(
        'Show drivers', ['All drivers', 'Done', 'No record', 'Needs review', 'Unsafe'],
        default='All drivers', key='daily-board-status') or 'All drivers'
    if selected_status == 'Done':
        rows = rows[rows.inspections_on_date.gt(0)]
    elif selected_status != 'All drivers':
        rows = rows[rows.daily_status.eq({'No record': 0, 'Needs review': 2, 'Unsafe': 3}[selected_status])]
    search_column, size_column = st.columns([5, 1])
    query = search_column.text_input('Search daily drivers', placeholder='Driver name, ID, vehicle or safety officer')
    size = size_column.selectbox('Rows per page', [25, 50, 100], key='daily-board-size-table')
    if query.strip():
        found = pd.Series(False, index=rows.index)
        for field in ('driver_id', 'driver_name', 'assigned_safety_officer', 'vehicle_names'):
            found |= rows[field].fillna('').astype(str).str.casefold().str.contains(query.strip().casefold(), regex=False)
        rows = rows[found]
    rows = rows.sort_values(['driver_name', 'driver_id'], na_position='last').copy()
    rows['inspection_date'] = selected
    st.caption(f'{len(rows):,} matching drivers · {selected:%b %d, %Y}')
    export_columns = ['driver_id', 'driver_name', 'assigned_safety_officer', 'inspection_date', 'daily_mark',
                      'inspections_on_date', 'days_with_recorded_PTIs', 'submission_frequency',
                      'training_follow_up', 'vehicle_names', 'vehicle_ids', 'trailer_ids',
                      'last_PTI_in_available_history', 'Cogo_listed_companions_unverified']
    st.download_button('Download daily driver CSV', csv_bytes(rows[export_columns]),
                       f'drivers-{selected.isoformat()}.csv', mime='text/csv', key='daily-board-download')
    if rows.empty:
        st.info('No drivers match this date and selection. Try another status or clear the search.')
        return
    details = st.checkbox('Show equipment IDs, training and crew', key='daily-table-details')
    pages = ceil(len(rows) / size)
    signature = (selected.isoformat(), selected_status, query, size, tuple(rows.driver_id))
    if st.session_state.get('daily-table-page-signature') != signature:
        st.session_state['daily-table-page'] = 1
        st.session_state['daily-table-page-signature'] = signature
    page = st.selectbox('Driver table page', range(1, pages + 1), key='daily-table-page',
                        format_func=lambda value: f'Page {value} of {pages}')
    current = rows.iloc[(page - 1) * size:page * size].copy()
    current['recorded_day_label'] = current.days_with_recorded_PTIs.astype(str) + f'/{len(scope.dates)}'
    display_columns = {
        'driver_name': 'Driver', 'driver_id': 'Driver ID', 'assigned_safety_officer': 'Safety officer',
        'vehicle_names': 'Vehicles in report',
        'daily_mark': 'Status', 'inspections_on_date': 'Inspections',
        'recorded_day_label': 'Days recorded', 'last_PTI_in_available_history': 'Last done',
    }
    if details:
        display_columns.update({'vehicle_ids': 'Vehicle IDs',
                                'trailer_ids': 'Trailer IDs', 'training_follow_up': 'Training follow-up',
                                'Cogo_listed_companions_unverified': 'Listed crew'})
    display = current[list(display_columns)].rename(columns=display_columns)
    colors = {label: (color, background) for label, color, background in STATUS.values()}
    def status_style(value):
        color, background = colors[value]
        return f'color: {color}; background-color: {background}; font-weight: 600'
    st.dataframe(display.style.map(status_style, subset=['Status']), hide_index=True,
                 width='stretch', height=min(650, 38 * len(display) + 40),
                 column_config={'Driver': st.column_config.TextColumn(width='medium'),
                                'Status': st.column_config.TextColumn(width='small'),
                                'Driver ID': st.column_config.TextColumn(width='small')},
                 key='daily-driver-table')
