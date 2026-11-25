"""Roster-first visual board with availability, authorship and holiday calendars."""
from datetime import timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from ..analytics import daily_status
from ..filters import Scope, reporting_dates
from ..roster import has_roster, roster_metadata, roster_summary, roster_daily, roster_links
from ..roster_audit import roster_audit
from .charts import GREEN, GRAY, RED, YELLOW, chart, show
from .kpi_cards import metrics
from .tables import table, display_times
from .workforce_groups import workforce_filters, render_teams, render_review, solo_totals

PURPLE = '#8b5bb5'


def render_roster_board(context):
    data = context.data
    st.title('Driver roster, holidays & PTI')
    if not has_roster(data):
        st.info('Upload the combined TMS/Samsara roster JSON to see availability, holidays and linked co-drivers.')
        return
    report_dates = context.scope.dates
    options = list(reversed(report_dates))
    selected = st.selectbox('Roster report date', options, format_func=lambda value: value.strftime('%a, %b %d, %Y'))
    dates = reporting_dates(len(report_dates), selected)
    summary = roster_summary(data, dates, selected)
    summary = summary[summary.driver_id.isin(context.scope.drivers.driver_id)].copy()
    summary, account_status, arrangement, submission_pattern = workforce_filters(summary,data,dates,context.timezone)
    if summary.empty:
        st.info('No matched roster drivers meet the selected account status, arrangement and submission filters.')
        render_review(context, dates, account_status)
        return
    available = summary.availability.eq('Available')
    holiday = ~available
    metrics([('Drivers in roster', len(summary)), ('Available · not on holiday', int(available.sum())),
             ('On holiday', int(holiday.sum())), ('Own PTI on selected date', int(summary.PTI_on_selected_date.sum()))])
    st.caption(f'{dates[0]:%b %d}–{dates[-1]:%b %d, %Y} · Availability uses your holiday dates. '
               'Recent activity means recorded PTI, not verified driving or employment status.')
    roster, calendar, crew, review, checks = st.tabs(['Roster & groups','Driver calendar & DVIRs','Co-driver teams','Needs review','Data checks'])
    with roster:
        left, right = st.columns(2)
        with left:
            st.markdown('**Available and on holiday**')
            frame = summary.availability.value_counts().rename_axis('availability').reset_index(name='drivers')
            fig = px.pie(frame, names='availability', values='drivers', hole=.65, color='availability',
                         color_discrete_map={'Available': GREEN, 'On holiday': PURPLE})
            fig.update_traces(textinfo='label+value')
            show(fig, 'roster-holiday-availability')
        with right:
            counts = summary.recent_activity.value_counts().rename_axis('activity').reset_index(name='drivers')
            chart('When drivers last recorded their own PTI', counts, 'drivers','activity',horizontal=True)
        daily = roster_daily(data, dates, summary.driver_id)
        st.markdown('**Drivers recording their own PTI each day**')
        fig = px.line(daily,x='date',y='drivers_with_own_PTI',markers=True,text='drivers_with_own_PTI',
                      custom_data=['available','on_holiday','available_without_own_PTI'],
                      color_discrete_sequence=[GREEN], labels={'date':'','drivers_with_own_PTI':'Drivers with own PTI'})
        fig.update_traces(textposition='top center',cliponaxis=False,
                          hovertemplate='%{x|%b %d}<br>Own PTI: %{y}<br>Available: %{customdata[0]}'
                                        '<br>On holiday: %{customdata[1]}<br>Available without own record: %{customdata[2]}<extra></extra>')
        fig.update_xaxes(dtick='D1',tickformat='%b %d')
        fig.update_yaxes(range=[0,max(1,daily.drivers_with_own_PTI.max())*1.2])
        show(fig,'roster-daily-activity',height=310)
        left, right = st.columns(2)
        with left:
            consistency = summary.consistency.value_counts().rename_axis('group').reset_index(name='drivers')
            chart('Regular, intermittent and no matched DVIR', consistency, 'drivers', 'group', horizontal=True,
                  color='group', colors={'Regular':GREEN,'Intermittent':YELLOW,'No matched DVIR':GRAY})
        with right:
            top = summary[summary.PTI_records.gt(0)].sort_values(['PTI_records','driver_id'],ascending=[False,True]).head(15).copy()
            top['driver'] = top.driver_name + ' (' + top.driver_id + ')'
            chart('Highest own PTI by driver', top, 'PTI_records', 'driver', horizontal=True)
        with st.expander('Safe, resolved and unsafe source statuses'):
            from ..stakeholder import reported_safety_groups
            chart('Reported safety status by DVIR author', reported_safety_groups(context.scope.records,
                  context.filtered_source_rows, set(summary.driver_id)), 'status', 'drivers', color='status',
                  colors={'Safe':GREEN,'Resolved':'#4586be','Unsafe':RED,'Unknown':GRAY})
            st.caption('Grouped source statuses cover supplied history and may not identify the status of each individual inspection.')
        st.subheader('Driver groups')
        masks = {'All roster drivers':pd.Series(True,index=summary.index), 'Available':available,
                 'On holiday':holiday, 'PTI in last 0–2 days':summary.recent_activity.eq('PTI in last 0–2 days'),
                 'Returned from holiday in last 3 days':summary.returned_recently,
                 'Regular PTI':summary.consistency.eq('Regular'), 'Intermittent PTI':summary.consistency.eq('Intermittent'),
                 'No own PTI in selected window':summary.PTI_records.eq(0) & ~summary.date_attribution_review,
                 'Needs individual DVIR detail':summary.date_attribution_review,
                 'Needs Samsara ID':summary.needs_samsara_id, 'Identity needs review':summary.identity_review}
        group = st.selectbox('Roster group',list(masks),format_func=lambda key:f'{key} · {int(masks[key].sum()):,}')
        st.caption('Regular = at least 4 of 7 dates or 8 of 15. Nonholiday dates without PTI are follow-up dates, not verified missed required inspections.')
        visible = ['driver_name','driver_id','vehicle_names','samsara_status','driver_mode','availability','recent_activity','PTI_records','recorded_dates',
                   'consistency','last_done','holiday_dates_in_window','nonholiday_dates_without_PTI',
                   'available_since_last_holiday','training','tms_id','cogo_id','id_match_basis','identity_review']
        shown = summary.loc[masks[group]].copy()
        if arrangement == 'Solo':
            shown = solo_totals(data, shown)
            visible += ['source_vehicle_count_full_file','source_trailer_count_full_file','source_totalPTI_full_file']
        table(shown.reindex(columns=visible),'roster-driver-summary',size=25,
              sort_columns=('driver_name','PTI_records','recorded_dates','last_done'))
        with st.expander('Daily holiday and activity totals'):
            table(daily,'roster-daily-totals',size=15)
    with calendar:
        st.subheader('Each driver’s calendar and inspections')
        names = summary.set_index('driver_id').driver_name.to_dict()
        driver = st.selectbox('Roster driver', sorted(names,key=names.get),format_func=lambda key:f'{names[key]} ({key})')
        entry = summary.set_index('driver_id').loc[driver]
        st.write(f"**{names[driver]}** · {entry.vehicle_names} · {entry.availability} · {entry.consistency}")
        metadata = roster_metadata(data)[driver]
        records = data.dvir_records[data.dvir_records.inspection_date.isin(dates)]
        scope = Scope(dates,data.drivers,records,data.dvir_records[data.dvir_records.inspection_time.isna()])
        marks = daily_status(scope,[driver]).iloc[0].tolist()
        labels = {0:'No own DVIR',1:'PTI recorded',2:'Needs review',3:'Unsafe',4:'On holiday'}
        calendar_rows = []
        for i,day in enumerate(dates):
            on_holiday = day in metadata['holidays']
            if marks[i] == 0 and on_holiday:
                marks[i] = 4
            calendar_rows.append({'driver_id':driver,'driver_name':names[driver],'vehicle_names':entry.vehicle_names,
                                  'date':day,'status':labels[marks[i]],'holiday_date':on_holiday})
        fig = go.Figure(go.Heatmap(z=[marks],x=[d.strftime('%b %d') for d in dates],y=[names[driver]],
                                  text=[[labels[value] for value in marks]],zmin=0,zmax=4,
                                  colorscale=[[0,GRAY],[.25,GREEN],[.5,YELLOW],[.75,RED],[1,PURPLE]],
                                  colorbar=dict(tickvals=list(labels),ticktext=list(labels.values())),
                                  hovertemplate='%{x}<br>%{text}<extra></extra>'))
        show(fig,'roster-driver-calendar',height=180)
        st.caption('Purple = holiday without an inspection. An actual inspection is retained even if the date is listed as holiday.')
        status = st.selectbox('Calendar dates',['All dates','No own DVIR','On holiday','PTI recorded','Unsafe','Needs review'])
        frame = pd.DataFrame(calendar_rows)
        table(frame if status=='All dates' else frame[frame.status.eq(status)],'roster-driver-calendar-dates',size=15)
        own = data.dvir_records[data.dvir_records.author_id.eq(driver) & data.dvir_records.inspection_date.le(selected)]
        st.markdown('**Own DVIR history in the supplied file**')
        columns=['dvir_id','author_id','author_name','inspection_time','inspection_type','vehicle_name','vehicle_id','trailer_id','safety_status']
        table(display_times(own[columns],context.timezone),'roster-own-dvir-history',size=25)
        if own.empty:
            st.info('No authored DVIR matched this roster driver in the supplied history. A partner’s inspections are shown separately in Co-drivers.')
        st.page_link('pages/7_DVIR_History.py',label='Open saved DVIR history and backups')
    with crew:
        render_teams(context, dates, account_status, set(summary.driver_id), submission_pattern)
    with review:
        render_review(context, dates, account_status)
    with checks:
        st.subheader('Data and merge checks')
        st.caption('Review items can be legitimate situations. Information items explain valid join repetition and source limitations.')
        issues = roster_audit(data)
        counts = issues.severity.value_counts()
        metrics([('Errors',int(counts.get('Error',0))),('Review items',int(counts.get('Review',0))),
                 ('Information',int(counts.get('Information',0)))])
        level = st.selectbox('Check severity',['All','Error','Review','Information'])
        table(issues if level=='All' else issues[issues.severity.eq(level)],'roster-data-checks',size=25)
