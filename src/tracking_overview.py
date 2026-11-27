"""Stakeholder tracking snapshot based on the TruckMate roster and 15 dates."""
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .upload_model import people_summary
from .components.charts import BLUE, GREEN, YELLOW, RED, show
from .components.kpi_cards import colored_metrics
from .tracking_review import attach_tracking_review


CARD_DETAILS={
    'TruckMate roster drivers':('blue','Primary roster drivers · counted once'),
    'Drivers with DVIR':('green','Own or linked co-driver submission · 15 days'),
    'Drivers without DVIR':('amber','Neither linked driver submitted · check context'),
    'DVIR submissions':('blue','Dated inspection entries · people counted separately'),
    'Has days off':('purple','At least one reported date off · 15 days'),
    'No days off reported':('blue','Zero or Not supplied · 15 days'),
    'No DVIR · no days off reported':('amber','Check work schedule and source information'),
    'No DVIR · has days off':('purple','Check dates off before following up'),
    'PTI training Done':('green','Uploaded training value is DONE'),
    'PTI training Not done':('amber','Includes missing or unrecognized training values'),
    'Trained in these 15 days':('blue','Done plus a known date inside this period'),
    'Training Done · no DVIR':('amber','Check training timing and dates worked'),
    'Training Not done · own DVIR in 15 days':('amber','Own dated submission · training record to verify'),
    'Training Not done · dated own DVIR in file':('amber','Whole uploaded history up to Report ending'),
    'Training Not done · co-driver coverage only':('purple','Partner submitted · no own submission in period'),
    'Drivers who submitted on a marked day off':('purple','Exact own-submission date matches a date off'),
    'Drivers with source data checks':('amber','Unique roster drivers · includes linked partner findings'),
    'Training records to review':('amber','Training value or completion date needs verification'),
    'No-submission follow-up':('amber','Zero period coverage · check training and days off'),
    'Drivers with no review flagged':('green','No source or tracking review currently identified'),
}


def _cards(values):
    colored_metrics(values,details=CARD_DETAILS)


@dataclass
class TrackingSnapshot:
    dates: list
    roster: pd.DataFrame
    events: pd.DataFrame
    daily: pd.DataFrame


def tracking_snapshot(report, end):
    dates=[end-timedelta(days=i) for i in reversed(range(15))]
    summary=people_summary(report,dates,end)
    roster=summary[summary.in_roster].copy()
    roster['Submitted']=roster.covered_dates_in_period.gt(0)
    roster['Days off group']=roster.holiday_dates_in_period.gt(0).map(
        {True:'Has days off',False:'No days off reported'})
    roster['Driver group']=roster.has_crew.map({True:'Co-driver',False:'Solo'})
    roster['Recently trained']=[
        r.pti_training_status=='Done' and r.training_completed_date in dates
        for r in roster.itertuples()]
    roster['Submission pattern']=roster.coverage_consistency.map(
        lambda value:{'Regular':'Regular','Intermittent':'Some dates recorded',
                      'No record in period':'No submission'}.get(value,'Training or date review'))
    # Count each author event once, even if a linked partner covers multiple roster members.
    roster_ids=set(roster.driver_id)
    authors=set(roster_ids)
    for crew in report.teams.to_dict('records'):
        if crew['members'] & roster_ids:
            authors.update(crew['members'])
    selected=report.events[report.events.driver_id.isin(authors)
        & report.events.inspection_date.isin(dates)].copy()
    own_dates=selected.groupby('driver_id').inspection_date.agg(set).to_dict()
    roster['Own DVIR on day off']=[bool(own_dates.get(row.driver_id,set()) & row.holidays)
                                 for row in roster.itertuples()]
    roster['Training not done with own DVIR']=roster.pti_training_status.ne('Done') & roster.dated_PTIs.gt(0)
    history=report.events[report.events.inspection_time.notna() & report.events.inspection_date.le(end)]
    file_counts=history.groupby('driver_id').size()
    roster['Own dated DVIRs in file']=roster.driver_id.map(file_counts).fillna(0).astype(int)
    roster['Training not done with dated own DVIR in file']=(
        roster.pti_training_status.ne('Done') & roster['Own dated DVIRs in file'].gt(0))
    counts=selected.groupby('inspection_date').size()
    own=selected[selected.driver_id.isin(set(roster.driver_id))].groupby('inspection_date').driver_id.nunique()
    daily=pd.DataFrame({'Date':dates,'DVIR submissions':[int(counts.get(d,0)) for d in dates],
        'Drivers covered':[sum(d in values for values in roster.coverage_dates) for d in dates],
        'Own submissions by roster drivers':[int(own.get(d,0)) for d in dates]})
    roster=attach_tracking_review(report,roster)
    return TrackingSnapshot(dates,roster,selected,daily)


def training_review_top_five(snapshot):
    """Review full uploaded history up to report end; preserve own authorship."""
    return snapshot.roster[snapshot.roster['Training not done with dated own DVIR in file']].sort_values(
        ['last_done','Own dated DVIRs in file','driver_id'],ascending=[False,False,True],kind='stable').head(5)


def _panel_heading(title,description):
    st.markdown(f'#### {title}')
    st.caption(description)


def _donut(labels,values,colors,key,center):
    fig=go.Figure(go.Pie(labels=labels,values=values,hole=.76,sort=False,
        marker_colors=colors,textinfo='value',textposition='outside',
        hovertemplate='%{label}<br>%{value:,} drivers · %{percent}<extra></extra>'))
    fig.update_layout(annotations=[dict(text=f'<b>{center:,}</b><br>drivers',x=.5,y=.5,
        showarrow=False,font_size=21)],legend=dict(orientation='h',y=-.12,x=.5,xanchor='center'))
    show(fig,key,height=290)


def render_tracking_overview(report,end,driver_table):
    snap=tracking_snapshot(report,end)
    r=snap.roster
    submitted=r.Submitted
    trained=r.pti_training_status.eq('Done')
    has_days=r.holiday_dates_in_period.gt(0)
    st.markdown('''<style>
    [data-testid="stMetricLabel"] {height:auto;min-height:3rem;}
    [data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] > div {
        white-space:normal !important;overflow:visible !important;text-overflow:clip !important;
        font-size:.96rem !important;font-weight:650;line-height:1.35;
    }
    [data-testid="stMetricValue"] {font-weight:700;font-variant-numeric:tabular-nums;}
    [data-testid="stHeading"] h4 {font-size:1.14rem;font-weight:700;line-height:1.35;}
    </style>''',unsafe_allow_html=True)
    st.subheader('Fleet at a glance · 15 days')
    st.caption(f'{snap.dates[0]:%b %d, %Y} – {end:%b %d, %Y} · TruckMate roster drivers · '
               'Either the driver or their linked co-driver submitting counts as covered.')
    _cards([('TruckMate roster drivers',len(r)),('Drivers with DVIR',int(submitted.sum())),
        ('Drivers without DVIR',int((~submitted).sum())),('DVIR submissions',len(snap.events))])
    if r.empty:
        st.info('No TruckMate roster drivers were found in this upload. Check Data checks & unmatched.')
        return
    percentage=100*submitted.mean()
    st.progress(float(submitted.mean()),text=f'{percentage:.1f}% of roster drivers have own or co-driver coverage in these 15 days')
    st.caption(f'{int(r.dated_PTIs.gt(0).sum()):,} drivers submitted their own DVIR · '
        f'{int((submitted & r.dated_PTIs.eq(0)).sum()):,} covered through a co-driver only. '
        'Submission totals count each inspection entry once, including linked partners; people and inspections are different totals.')

    st.subheader('Days off and recording gaps')
    st.markdown('**Which drivers need a closer look?** Compare submission activity with reported days off.')
    _cards([('Has days off',int(has_days.sum())),('No days off reported',int((~has_days).sum())),
        ('No DVIR · no days off reported',int((~submitted & ~has_days).sum())),
        ('No DVIR · has days off',int((~submitted & has_days).sum()))])
    st.caption('All counts use the same 15-day window. No days off reported includes zero and Not supplied. '
        'No DVIR means neither the driver nor a linked co-driver submitted a dated inspection in this period.')

    st.subheader('Coverage and participation')
    left,right=st.columns(2)
    with left,st.container(border=True):
        _panel_heading('DVIR submission coverage','Roster drivers with an own or linked co-driver submission in these 15 days.')
        _donut(['Submitted in period','No submission in period'],[int(submitted.sum()),int((~submitted).sum())],
               [GREEN,RED],'view-tracking-submission',len(r))
    with right,st.container(border=True):
        _panel_heading('PTI training completion','Uploaded training status for every TruckMate roster driver.')
        _donut(['Done','Not done'],[int(trained.sum()),int((~trained).sum())],
               [BLUE,YELLOW],'view-tracking-training',len(r))

    left,right=st.columns(2)
    with left,st.container(border=True):
        _panel_heading('Days off and submissions in the period','Compare drivers with reported days off against those with none reported.')
        chart=r.assign(Coverage=submitted.map({True:'Submitted in period',False:'No submission in period'}))
        counts=chart.groupby(['Days off group','Coverage']).size().reset_index(name='Drivers')
        fig=px.bar(counts,x='Days off group',y='Drivers',color='Coverage',text='Drivers',
            barmode='stack',color_discrete_map={'Submitted in period':GREEN,'No submission in period':RED})
        fig.update_layout(legend=dict(orientation='h',y=-.25),xaxis_title=None)
        fig.update_yaxes(dtick=1 if len(r)<10 else None)
        show(fig,'view-tracking-days-off',height=310)
        st.caption('Days off and submissions may fall on different dates within the same 15 days. '
            'No days off reported includes zero and Not supplied.')
    with right,st.container(border=True):
        _panel_heading('Coverage by driver arrangement','Each roster driver counts once. Either linked driver submitting gives coverage.')
        counts=chart.groupby(['Driver group','Coverage']).size().reset_index(name='Drivers')
        fig=px.bar(counts,x='Driver group',y='Drivers',color='Coverage',text='Drivers',
            barmode='stack',color_discrete_map={'Submitted in period':GREEN,'No submission in period':RED})
        fig.update_layout(legend=dict(orientation='h',y=-.25),xaxis_title=None)
        fig.update_yaxes(dtick=1 if len(r)<10 else None)
        show(fig,'view-tracking-arrangement',height=310)

    with st.container(border=True):
        _panel_heading('Recording consistency','Count separate dates with a submission, rather than the number of inspections.')
        order=['Regular','Some dates recorded','No submission','Training or date review']
        counts=r['Submission pattern'].value_counts().reindex(order,fill_value=0)
        fig=go.Figure(go.Bar(x=counts.values,y=counts.index,orientation='h',
            marker_color=[GREEN,YELLOW,RED,BLUE],text=counts.values,textposition='auto',
            hovertemplate='%{y}<br>%{x:,} roster drivers<extra></extra>'))
        fig.update_yaxes(autorange='reversed')
        fig.update_layout(xaxis_title='TruckMate roster drivers')
        show(fig,'view-tracking-regularity',height=250)
        st.caption('Regular = at least 8 of these 15 dates covered by an own or linked co-driver DVIR. '
            'Some dates recorded = 1–7 dates. Training/date exceptions are shown separately. '
            'Multiple DVIRs on one date count as one participation date.')

    left,right=st.columns(2)
    with left,st.container(border=True):
        _panel_heading('Daily driver participation','Compare own submissions with own-or-co-driver coverage. Values count drivers.')
        series=snap.daily.melt(id_vars='Date',value_vars=['Drivers covered','Own submissions by roster drivers'],
            var_name='Measure',value_name='Drivers')
        fig=px.line(series,x='Date',y='Drivers',color='Measure',markers=True,
            color_discrete_sequence=[GREEN,BLUE])
        fig.update_xaxes(dtick=172800000,tick0=snap.dates[0],tickformat='%b %d',
                         range=[snap.dates[0],snap.dates[-1]])
        fig.update_yaxes(rangemode='tozero')
        fig.update_layout(legend=dict(orientation='h',y=-.28))
        show(fig,'view-tracking-daily-drivers',height=320)
    with right,st.container(border=True):
        _panel_heading('Daily inspection volume','Each dated DVIR entry counts once. Several entries may belong to one driver.')
        fig=px.bar(snap.daily,x='Date',y='DVIR submissions',text='DVIR submissions',
                   color_discrete_sequence=[BLUE])
        fig.update_xaxes(dtick=172800000,tick0=snap.dates[0],tickformat='%b %d')
        show(fig,'view-tracking-daily-entries',height=320)

    st.divider()
    st.subheader('Training status and follow-up')
    st.caption('Review the training record after checking submission activity above. '
        'These counts describe the uploaded training information; a DVIR is not proof of completed training.')
    _cards([('PTI training Done',int(trained.sum())),('PTI training Not done',int((~trained).sum())),
        ('Trained in these 15 days',int(r['Recently trained'].sum())),
        ('Training Done · no DVIR',int((trained & ~submitted).sum()))])
    st.caption('Recently trained requires Done and one known training date within these 15 days. '
        'Check training timing before following up about missing DVIRs.')
    _panel_heading('Training status needs verification','Submission evidence is available, but the uploaded training value is not DONE.')
    _cards([('Training Not done · own DVIR in 15 days',int(r['Training not done with own DVIR'].sum())),
        ('Training Not done · dated own DVIR in file',int((~trained & r.last_done.notna()).sum())),
        ('Training Not done · co-driver coverage only',int((~trained & submitted & r.dated_PTIs.eq(0)).sum()))])
    st.caption('A dated DVIR does not change the uploaded training status. Not done includes blank or missing '
        'training values: verify the training record. File history here uses dated own submissions up to Report ending.')
    with st.expander('Top 5 · Training Not done with a dated DVIR in the file',expanded=True):
        top=training_review_top_five(snap)
        st.markdown('**Whole uploaded file · own dated submissions**')
        st.caption('Includes records older than the 15-day window, up to Report ending. '
            'Most recent own DVIR date first, then whole-file submission count. '
            'Use Tracking list below for the complete list and CSV download.')
        if top.empty:
            st.info('No roster drivers have training Not done and an own dated DVIR in the uploaded history up to Report ending.')
        else:
            visible=top[['tms_id','driver_name','driver_id','vehicle_names','pti_training_status',
                'Own dated DVIRs in file','dated_PTIs','last_done']].rename(columns={'tms_id':'TMW ID','driver_name':'Driver',
                'driver_id':'Driver ID','vehicle_names':'Vehicles','pti_training_status':'PTI training',
                'dated_PTIs':'Own DVIRs · 15 days','Own dated DVIRs in file':'Own dated DVIRs · file',
                'last_done':'Latest own DVIR'})
            st.table(visible.reset_index(drop=True),hide_index=True)

    with st.expander('Data check · submissions on marked days off',expanded=False):
        _cards([('Drivers who submitted on a marked day off',int(r['Own DVIR on day off'].sum()))])
        st.caption('The same driver personally submitted on an exact date marked as their day off. '
            'Check whether the date off or work schedule needs updating; this is a data check, not a conclusion about the driver.')

    st.divider()
    st.subheader('Driver lists and next steps')
    _cards([('Drivers with source data checks',int(r.source_review_items.gt(0).sum())),
        ('Training records to review',int((~trained | r.training_date_conflict).sum())),
        ('No-submission follow-up',int((~submitted).sum())),
        ('Drivers with no review flagged',int(r.review_category.isin(['No review flagged','Source information']).sum()))])
    st.caption('A driver may appear in more than one review card. Source checks cover the whole upload; '
        'submission follow-up uses these 15 days. Suggested next steps do not change source records.')
    with st.container(border=True):
        _panel_heading('Explore the matching drivers','Choose a tracking list, open individual profiles, or download the filtered CSV.')
        options={
            'Choose a list':None,
            'Data checks · drivers needing review':~r.review_category.isin(['No review flagged','Source information']),
            'Source data checks only':r.source_review_items.gt(0),
            'With DVIR in these 15 days':submitted,
            'Without DVIR in these 15 days':~submitted,
            'No DVIR · no days off reported':~submitted & ~has_days,
            'No DVIR · has days off':~submitted & has_days,
            'Training Done · no DVIR':trained & ~submitted,
            'PTI training Not done':~trained,
            'Training Not done · own DVIR in 15 days':r['Training not done with own DVIR'],
            'Training Not done · dated own DVIR in file':~trained & r.last_done.notna(),
            'Drivers who submitted on a marked day off':r['Own DVIR on day off'],
            'Trained in these 15 days':r['Recently trained'],
            'Regular · at least 8 dates':r['Submission pattern'].eq('Regular'),
            'Some dates recorded · 1–7 dates':r['Submission pattern'].eq('Some dates recorded'),
            'No DVIR evidence in the uploaded file':~r.has_covered_DVIR,
        }
        choice=st.selectbox('Tracking list',list(options),key='view-tracking-list')
        if options[choice] is not None:
            selected=r[options[choice]].copy()
            st.write(f'**{len(selected):,} matching roster drivers**')
            driver_table(selected,'tracking-drilldown',[
                'tms_id','driver_name','driver_id','vehicle_names','arrangement','pti_training_status',
                'pti_training_date','training_period_status','dated_PTIs','partner_PTIs_in_period',
                'covered_dates_in_period','coverage_consistency','Own dated DVIRs in file','last_done','last_covered_dvir_in_file',
                'availability','holiday_dates_in_period','holiday_dates_display',
                'review_category','data_checks','check_details','suggested_next_step'],
                sort_columns=('driver_name','dated_PTIs','covered_dates_in_period'))
        st.caption('These tracking lists include all TruckMate roster drivers. The Simple 15-day report '
            'applies its trained-only rule to the solo and No PTI in entire file tables.')
        st.page_link('pages/9_Unmatched_Review.py',label='Open all source checks and unmatched authors')
    left,right=st.columns(2)
    with left:st.page_link('pages/12_Simple_Report.py',label='Open Simple 15-day report',icon='📋')
    with right:st.page_link('pages/13_PTI_Training.py',label='Open PTI training not done',icon='🎓')
