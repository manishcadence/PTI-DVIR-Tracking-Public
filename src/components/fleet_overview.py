"""A stakeholder-facing summary with trends and actionable follow-up lists."""
import pandas as pd
import plotly.express as px
import streamlit as st

from ..analytics import driver_activity, recorded_inspections
from ..filters import officer_key, officer_labels
from ..history import history_summary
from ..source_associations import source_associations
from ..source_audit import duplicate_drivers
from ..stakeholder import officer_summary, recording_groups, recency_groups, reported_safety_groups, driver_pti_totals
from .charts import GRAY, GREEN, RED, YELLOW, chart, show
from .kpi_cards import metrics
from .rating_export import rating_download
from .tables import display_times, table
from .daily_participation import render_daily_participation


def safety_chart(context, drivers, records):
    chart('Safe, resolved and unsafe', reported_safety_groups(
        records, context.filtered_source_rows, set(drivers.driver_id)),
        'status', 'drivers', color='status',
        colors={'Safe': GREEN, 'Resolved': '#4586be', 'Unsafe': RED, 'Unknown': GRAY})
    st.caption('One source-reported priority status per driver: unsafe, resolved, other non-safe, then safe. '
               'Grouped statuses cover the supplied file; they do not establish current equipment condition.')


def ranking_chart(context, drivers, *, dated):
    totals = driver_pti_totals(drivers, context.filtered_source_rows)
    if dated:
        totals = totals.merge(drivers[['driver_id', 'submissions']], on='driver_id', how='left')
    choices = {}
    if dated:
        choices['Recorded inspections · selected period'] = 'submissions'
    if context.data.source_rows:
        choices['Vehicle + trailer PTIs · supplied file'] = 'combined_equipment_PTIs'
        choices['Reported totalPTI · supplied source rows'] = 'source_totalPTI'
    selected = st.selectbox('Rank drivers by', list(choices), key='overview-ranking-basis')
    measure = choices[selected]
    frame = totals.loc[totals[measure].gt(0)].sort_values(
        [measure, 'driver_id'], ascending=[False, True]).head(15).copy()
    frame['driver'] = frame.driver_name.fillna('Unknown') + ' (' + frame.driver_id + ')'
    st.markdown('**Highest PTI by driver**')
    if frame.empty:
        st.caption('No positive PTI totals match the current filters.')
    else:
        figure = px.bar(frame, x=measure, y='driver', orientation='h',
                        labels={measure: 'PTIs', 'driver': ''}, color_discrete_sequence=[GREEN])
        figure.update_yaxes(autorange='reversed')
        show(figure, 'overview-highest-pti', height=max(300, 26 * len(frame) + 50))
    st.caption('Equipment PTIs count nonempty vehicle/trailer list entries from every source row. '
               'Reported totalPTI is a separate supplied count; neither gives distinct inspection dates.')


def render_summary_overview(context, drivers):
    """Keep the driver overview useful when an export has no inspection dates."""
    summary = driver_pti_totals(drivers, context.filtered_source_rows)
    has_evidence = summary.has_supplied_evidence
    metrics([('Drivers in supplied report', len(drivers)), ('With supplied PTI evidence', int(has_evidence.sum())),
             ('No supplied PTI evidence', int((~has_evidence).sum())),
             ('Vehicle + trailer PTIs', int(summary.combined_equipment_PTIs.sum()))])
    st.info('Inspection dates are missing from this export. Regular = at least 4 of 7 dates '
            '(8 of 15). Regular/intermittent counts, daily participation and last-done dates '
            'will return automatically when startTimes or endTimes are included.')
    activity, followup = st.tabs(['PTI activity', 'Driver follow-up'])
    with activity:
        left, right = st.columns([3, 2])
        with left:
            ranking_chart(context, drivers, dated=False)
        with right:
            safety_chart(context, drivers, context.scope.records)
            chart('Supplied driver activity', pd.DataFrame({
                'activity': ['With PTI evidence', 'No PTI evidence'],
                'drivers': [int(has_evidence.sum()), int((~has_evidence).sum())]}), 'activity', 'drivers')
        st.caption('PTI evidence means a nonzero reported totalPTI or a nonempty vehicle/trailer list. '
                   'These are full-file results, not a 7/15-day comparison.')
    with followup:
        masks = {'All drivers': pd.Series(True, index=summary.index),
                 'With PTI evidence': has_evidence, 'No PTI evidence': ~has_evidence}
        selected = st.selectbox('Driver group', list(masks),
                                format_func=lambda key: f'{key} · {int(masks[key].sum()):,}',
                                key='stakeholder-driver-group')
        table(summary.loc[masks[selected]].drop(columns='has_supplied_evidence'),
              'overview-undated-driver-summary', size=25,
              sort_columns=('driver_name', 'combined_equipment_PTIs', 'source_totalPTI'))
    with st.expander('Vehicle, trailer and listed crew details'):
        table(source_associations(context.filtered_source_rows), 'overview-undated-crew', size=25)
        st.caption('Listed crew comes from the supplied Cogo fields. Crew membership does not credit another driver’s inspection.')


def render_fleet_overview(context):
    from ..roster import has_roster
    if has_roster(context.data):
        from .roster_board import render_roster_board
        render_roster_board(context)
        return
    scope = context.scope
    drivers = driver_activity(scope)
    pti = recorded_inspections(scope.records)
    st.title('Fleet overview')
    st.caption('Driver inspection activity, equipment and follow-up priorities at a glance.')
    rating_download(context, 'overview')
    if drivers.empty:
        st.info('No drivers match the current filters. Clear a search to see the fleet.')
        return
    if context.data.source_rows and all('startTimes' not in row and 'endTimes' not in row
                                        for row in context.data.source_rows):
        render_summary_overview(context, drivers)
        return
    has_officers = officer_key(context.data.driver_assignments).ne('unknown').any()
    total = len(drivers)
    threshold = (len(scope.dates) + 1) // 2
    recorded = drivers.submissions.gt(0)
    regular = drivers.recorded_days.ge(threshold)
    no_record = drivers.activity.eq('No recorded PTI')
    unassigned = officer_key(drivers).eq('unknown')
    population_label = 'Drivers in supplied report' if context.data.retain_supplied_drivers else 'Drivers in report'
    metrics([(population_label, total), ('Regular · 4/7 or 8/15 dates', int(regular.sum())),
             ('Intermittent', int((recorded & ~regular).sum())), ('No recorded activity', int(no_record.sum()))])
    st.markdown(f'**{int(recorded.sum()):,} of {total:,} drivers** recorded a pre/post-trip inspection. '
                f'**{int(regular.sum()):,}** met the regular-recording threshold; '
                f'**{int(no_record.sum()):,}** have no record in this period.')
    st.caption(f'{scope.dates[0]:%b %d}–{scope.dates[-1]:%b %d, %Y} · Regular = at least '
               f'{threshold} of {len(scope.dates)} dates. Calendar gaps are follow-up items, not confirmed compliance misses.')
    labels = ['PTI activity', 'Driver follow-up'] + (['Safety officers'] if has_officers else []) + ['Training']
    tabs = st.tabs(labels)
    trends, followup, other = tabs[0], tabs[1], tabs[-1]
    lists = drivers.merge(history_summary(context.data, scope.dates[-1]), on='driver_id', how='left')
    lists['safety_officer'] = officer_labels(lists)
    list_columns = {'driver_name': 'driver', 'driver_id': 'driver_id', 'safety_officer': 'safety_officer',
                    'submissions': 'recorded_inspections', 'recorded_days': 'recorded_days',
                    'days_without_pti': 'calendar_days_without_record',
                    'last_pti_available_history': 'last_recorded_inspection'}
    if not has_officers:
        list_columns.pop('safety_officer')
    with trends:
        render_daily_participation(scope)
        left, right = st.columns(2)
        with left:
            chart('Recording consistency', recording_groups(drivers, len(scope.dates)),
                  'drivers', 'group', horizontal=True, color='group',
                  colors={'Regular': GREEN, 'Intermittent': YELLOW, 'No record': GRAY, 'Needs data review': RED})
        with right:
            chart('Time since last recorded inspection', recency_groups(lists), 'drivers', 'last_done', horizontal=True)
        st.caption('Recency uses all supplied inspection history, measured against the report’s activity end date.')
        left, right = st.columns([3, 2])
        with left:
            ranking_chart(context, drivers, dated=True)
        with right:
            safety_chart(context, drivers, pti)
    with followup:
        st.subheader('Find drivers to follow up with')
        masks = {'All drivers': pd.Series(True, index=drivers.index), 'Regular': regular,
                 'Intermittent': recorded & ~regular, 'No recorded activity': no_record,
                 'Unassigned officer': unassigned,
                 'Needs data review': drivers.activity.eq('Insufficient information')}
        if not has_officers:
            masks.pop('Unassigned officer')
        selected = st.selectbox('Driver group', list(masks),
                                format_func=lambda label: f'{label} · {int(masks[label].sum()):,}',
                                key='stakeholder-driver-group')
        ids = set(drivers.loc[masks[selected], 'driver_id'])
        table(lists.loc[lists.driver_id.isin(ids), list(list_columns)].rename(columns=list_columns),
              'overview-driver-follow-up', size=25,
              sort_columns=('driver', 'recorded_days', 'calendar_days_without_record'))
    if has_officers:
        with tabs[2]:
            st.subheader('Officer assignment and follow-up')
            assigned_count = total - int(unassigned.sum())
            st.progress(assigned_count / total, text=f'{assigned_count:,} of {total:,} drivers have an officer assignment · '
                        f'{int(unassigned.sum()):,} unassigned')
            ownership = officer_summary(drivers, len(scope.dates))
            if assigned_count:
                frame = ownership.melt(['officer_key', 'safety_officer'],
                                       value_vars=['regular', 'intermittent_or_review', 'no_record'],
                                       var_name='activity', value_name='driver_count')
                frame.activity = frame.activity.map({'regular': 'Regular', 'intermittent_or_review': 'Intermittent / review', 'no_record': 'No record'})
                duplicates = ownership.safety_officer.duplicated(keep=False)
                unique_labels = ownership.safety_officer.where(~duplicates,
                                  ownership.safety_officer + ' (' + ownership.officer_key + ')')
                labels = dict(zip(ownership.officer_key, unique_labels))
                frame['officer'] = frame.officer_key.map(labels)
                figure = px.bar(frame, x='driver_count', y='officer', color='activity', orientation='h',
                                color_discrete_map={'Regular': GREEN, 'Intermittent / review': YELLOW, 'No record': GRAY},
                                labels={'officer': '', 'driver_count': 'Drivers', 'activity': ''})
                figure.update_layout(barmode='stack', legend=dict(orientation='h', y=1.15))
                show(figure, 'overview-officer-coverage', height=max(320, 24 * len(ownership) + 90))
            else:
                st.info('No safety-officer assignments were supplied. All driver activity is still included under Unassigned.')
            table(ownership.drop(columns='officer_key'), 'officer-follow-up-summary')
            if unassigned.any():
                st.markdown('**Drivers needing an officer assignment**')
                table(lists.loc[lists.driver_id.isin(drivers.loc[unassigned, 'driver_id']), list(list_columns)]
                      .rename(columns=list_columns), 'unassigned-driver-review', size=25)
                st.caption('Use the Unassigned option in the sidebar to focus on these drivers. No assignment is guessed from names or shared equipment.')
    with other:
        st.subheader('Training coverage')
        training = drivers[['driver_id']].merge(context.data.training, on='driver_id', how='left')
        status = training.training_status.fillna('unknown').where(
            training.training_status.isin(['completed', 'incomplete', 'not_trained']), 'unknown')
        training_counts = status.map({'completed': 'Completed', 'incomplete': 'Incomplete',
                                     'not_trained': 'Not trained', 'unknown': 'Unknown'}).value_counts()
        if status.eq('unknown').all():
            st.write(f'{len(status):,} drivers have unknown training status.')
            st.caption('Training records have not been matched yet. Unknown does not mean not trained.')
        else:
            chart('Verified training status', training_counts.rename_axis('status').reset_index(name='drivers'),
                  'status', 'drivers')
    with st.expander('Source data and detailed inspection records'):
        if context.data.source_rows:
            st.caption(f'{len(context.data.source_rows):,} source rows · '
                       f'{context.data.drivers.driver_id.nunique():,} distinct driver IDs before filters.')
            audit = duplicate_drivers(context.data.source_rows)
            if not audit.empty:
                st.markdown('**Repeated driver IDs — source audit**')
                table(audit, 'duplicate-drivers', size=30)
            st.markdown('**Vehicle and crew source rows**')
            table(source_associations(context.filtered_source_rows), 'source-inspection-counts')
        columns = ['dvir_id', 'author_id', 'author_name', 'inspection_time', 'vehicle_name', 'vehicle_id',
                   'trailer_name', 'trailer_id', 'safety_status']
        st.markdown('**Dated pre/post-trip inspection records**')
        table(display_times(pti[columns], context.timezone), 'pre-trip-dvirs')
