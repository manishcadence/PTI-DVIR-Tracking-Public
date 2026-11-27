"""Managed upload-only fleet overview, driver lists, teams and individual detail."""
import hashlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from .upload_model import people_summary,crew_summary
from .local_ui import page_context
from .components.tables import csv_bytes,pretty,display_times
from .components.charts import GREEN,GRAY,YELLOW,BLUE,show
from .components.kpi_cards import metrics
from .components.dvir_calendar import calendar_figure

PURPLE='#8b5bb5'
DAYS_OFF_STATUS={'On holiday all period':'Days off all period','Partly on holiday':'Some days off',
                 'No holiday dates reported':'No days off reported','On holiday':'Day off'}
LABELS={'data_checks':'Data checks','check_details':'Check details','suggested_next_step':'Suggested next step',
        'review_category':'Review category','source_review_items':'Source review items',
        'safety_status_file':'Safety status (file)','safety_values_file':'All safety values (file)',
        'dvir_coverage':'DVIR coverage (own or co-driver)','coverage_consistency':'Consistency (own or co-driver)',
        'covered_dates_in_period':'Dates covered (own or co-driver)','has_own_DVIR':'Own DVIR evidence (file)',
        'last_covered_dvir_in_file':'Latest own/co-driver DVIR date (file)','training_period_status':'Training relative to report','pti_training_status':'PTI training','pti_training_date':'Training date (uploaded)',
        'training_done_no_dvir_in_period':'Training done · no DVIR in period','training_done_no_dvir_in_file':'Training done · no DVIR in file',
        'driver_name':'Driver','driver_id':'Driver ID','vehicle_names':'Vehicles in report','samsara_status':'Samsara status',
        'availability':'Days off status (period)','holiday_dates_in_period':'Days off in period',
        'holiday_dates_display':'Reported dates off','coverage_dates_without_recorded_holiday':'Dates without DVIR or reported day off','arrangement':'Arrangement','dated_PTIs':'DVIRs in period','recorded_dates':'Dates with DVIR',
        'needs_review':'Data review','consistency':'Consistency','last_done':'Last DVIR in file','reported_vehicle_count':'Vehicle PTIs (file)',
        'reported_trailer_count':'Trailer PTIs (file)','reported_totalPTI':'Reported PTIs (file)','tms_id':'TruckMate / TMW ID',
        'partner_PTIs_in_period':'Partner DVIRs in period','nonholiday_dates_without_record':'Dates without own DVIR or reported day off'}
CORE=['driver_name','driver_id','pti_training_status','pti_training_date','training_period_status','category','vehicle_names','samsara_status','availability','holiday_dates_in_period','holiday_dates_display','coverage_dates_without_recorded_holiday','arrangement','dated_PTIs','recorded_dates',
      'consistency','needs_review','last_done','last_covered_dvir_in_file','partner_PTIs_in_period','nonholiday_dates_without_record','reported_vehicle_count',
      'reported_trailer_count','reported_totalPTI','safety_status_file']


def context_summary():
    c=page_context()
    return c,people_summary(c.report,c.dates,c.end)


def caption(c):
    latest=f'latest uploaded inspection {c.report.latest:%b %d, %Y}' if c.report.events.inspection_time.notna().any() else 'no usable inspection dates supplied'
    st.caption(f'{c.dates[0]:%b %d}–{c.end:%b %d, %Y} · {latest} · {c.filename}')


def training_not_done():
    c,summary=context_summary()
    st.title('PTI training not done')
    caption(c)
    st.caption('TruckMate roster drivers whose PTI training value is not DONE. Empty, missing, Unknown, Not and other values are included as Not done. Actual DVIR submissions do not change training status.')
    frame=summary[summary.in_roster & summary.pti_training_status.eq('Not done')].copy()
    left,right=st.columns([2,1])
    query=left.text_input('Find a driver or vehicle',placeholder='Name, TMW ID, driver ID or vehicle',key='view-training-not-done-search')
    arrangement=right.selectbox('Driver arrangement',['All','Solo','Co-driver'],key='view-training-not-done-arrangement')
    if arrangement!='All':frame=frame[frame.has_crew.eq(arrangement=='Co-driver')]
    if query.strip():
        found=pd.Series(False,index=frame.index)
        for field in ('driver_name','driver_id','tms_id','vehicle_names'):
            found |= frame[field].fillna('').astype(str).str.contains(query.strip(),case=False,regex=False)
        frame=frame[found]
    st.markdown(f'**{len(frame):,} drivers with training not done**')
    table(frame,'training-not-done',[
        'tms_id','driver_name','driver_id','vehicle_names','arrangement','pti_training_status',
        'pti_training_date','training_period_status','dated_PTIs','last_covered_dvir_in_file','safety_status_file'],
        sort_columns=('driver_name','vehicle_names','dated_PTIs'))


def open_selected_driver(table_key,driver_ids):
    """Resolve the selected cell against the exact rendered page, using stable IDs."""
    cells=st.session_state.get(table_key,{}).get('selection',{}).get('cells',[])
    if not cells:return
    row,column=cells[0]
    if column not in ('Driver','Driver ID','Profile') or not isinstance(row,int) or not 0<=row<len(driver_ids):return
    st.session_state['view-profile-target']=driver_ids[row]
    st.session_state['view-profile-open']=True


def table(frame,key,columns=None,size=50,sort_columns=()):
    frame=frame.loc[:,[column for column in frame.columns if not column.startswith('_')]].copy()
    if 'availability' in frame:frame['availability']=frame.availability.map(lambda value:DAYS_OFF_STATUS.get(value,value))
    if sort_columns and not frame.empty:
        left,middle,right=st.columns([2,1,1])
        field=left.selectbox('Sort all matching rows by',list(sort_columns),format_func=lambda value:LABELS.get(value,value.replace('_',' ').title()),key=f'view-{key}-sort')
        descending=middle.toggle('Descending',value=False,key=f'view-{key}-descending')
        size=right.selectbox('Rows per page',[25,50,100],index=1,key=f'view-{key}-size')
        frame=frame.sort_values(field,ascending=not descending,na_position='last',kind='stable')
    export=frame if columns is None else frame.reindex(columns=columns)
    for column in export.columns:
        if export[column].dtype==object:
            export[column]=export[column].map(lambda x:', '.join(sorted(str(v) for v in x)) if isinstance(x,(set,list,tuple)) else x)
    st.download_button('Download CSV',csv_bytes(export),f'{key}.csv',mime='text/csv',key=f'view-{key}-csv')
    if frame.empty:
        st.info('No records match these filters.');return frame
    pages=max(1,(len(frame)+size-1)//size)
    state=f'view-{key}-page'
    signature=(tuple(frame.index),size)
    if st.session_state.get(state+'-signature')!=signature:
        st.session_state[state]=1;st.session_state[state+'-signature']=signature
    if st.session_state.get(state) not in range(1,pages+1): st.session_state[state]=1
    page=st.selectbox(f'Page · {len(frame):,} rows',range(1,pages+1),key=state) if pages>1 else 1
    selected=frame.iloc[(page-1)*size:page*size]
    for field in ('dated_PTIs','recorded_dates','reported_vehicle_count','reported_trailer_count','reported_totalPTI','partner_PTIs_in_period','nonholiday_dates_without_record','duration_records'):
        if field in export:export[field]=pd.to_numeric(export[field],errors='coerce').astype('Int64')
    visible=export.loc[selected.index].rename(columns=lambda name:LABELS.get(name,name.replace('_',' ').title().replace('Pti','PTI').replace('Dvir','DVIR').replace(' Id',' ID')))
    if {'Driver','Driver ID'}.issubset(visible.columns):
        driver_ids=tuple(selected.driver_id.astype(str))
        signature=hashlib.sha256(repr(driver_ids).encode()).hexdigest()[:16]
        table_key=f'view-{key}-driver-links-{signature}'
        visible.insert(visible.columns.get_loc('Driver')+1,'Profile','Open profile')
        st.caption('Click a driver name, Driver ID, or Open profile to view their individual report.')
        st.dataframe(visible,hide_index=True,width='stretch',height=min(650,38*len(visible)+40),
                     key=table_key,on_select=lambda:open_selected_driver(table_key,driver_ids),
                     selection_mode='single-cell',lazy=False)
    else:
        st.dataframe(visible,hide_index=True,width='stretch',height=min(650,38*len(visible)+40))
    return selected


def filters(frame,c,key,arrangement_filter=True,coverage=False):
    left,middle,right=st.columns([2,1,1])
    query=left.text_input('Search drivers',placeholder='Name, ID or vehicle',key=f'view-{key}-search')
    account=middle.selectbox('Samsara status',['All','Active','Deactivated','Unknown'],key=f'view-{key}-account')
    holiday=right.selectbox('Days off status (period)',['All','On holiday all period','Partly on holiday','No holiday dates reported','Unknown'],format_func=lambda value:DAYS_OFF_STATUS.get(value,value),key=f'view-{key}-holiday')
    left,right=st.columns(2)
    activity=left.selectbox('PTI activity',['All','Done on selected date','No record on selected date','Regular','Intermittent','No record in period','Needs review'],key=f'view-{key}-activity')
    arrangement=right.selectbox('Arrangement',['All','Solo / no crew information','Co-driver'],key=f'view-{key}-arrangement') if arrangement_filter else 'All'
    left,middle,right=st.columns([1,1.5,2])
    training=left.selectbox('PTI training',['All','Done','Not done'],key=f'view-{key}-training')
    timing=middle.selectbox('Training relative to report',[
        'All','Trained before period','Trained during period','Trained after period',
        'Training on report-ending date','Not trained','Training date unknown',
        'Training not recorded','Training dated after period','Training dates need review'],
        key=f'view-{key}-training-timing')
    followup=right.selectbox('Training / DVIR follow-up',['All','Training done · no DVIR in period','Training done · no DVIR in file','Training done · DVIR in file, none in period'],key=f'view-{key}-training-followup')
    if training!='All': frame=frame[frame.pti_training_status.eq(training)]
    if timing!='All':frame=frame[frame.training_period_status.eq(timing)]
    missing_period=frame.covered_dates_in_period.eq(0) if coverage else frame.dated_PTIs.eq(0)
    missing_file=~frame.has_covered_DVIR if coverage else ~frame.has_own_DVIR
    if followup=='Training done · no DVIR in period':frame=frame[frame.pti_training_status.eq('Done') & frame.training_followup_eligible & missing_period]
    elif followup=='Training done · no DVIR in file':frame=frame[frame.pti_training_status.eq('Done') & frame.training_followup_eligible & missing_file]
    elif followup=='Training done · DVIR in file, none in period':frame=frame[frame.pti_training_status.eq('Done') & frame.training_followup_eligible & ~missing_file & missing_period]
    if query.strip():
        found=pd.Series(False,index=frame.index)
        for field in ('driver_name','driver_id','vehicle_names'):
            found |= frame[field].fillna('').astype(str).str.contains(query.strip(),case=False,regex=False)
        frame=frame[found]
    if account!='All': frame=frame[frame.samsara_status.eq(account)]
    if holiday!='All': frame=frame[frame.availability.eq(holiday)]
    if arrangement!='All': frame=frame[frame.arrangement.eq(arrangement)]
    selected_date='covered_on_selected_date' if coverage else 'on_selected_date'
    consistency='coverage_consistency' if coverage else 'consistency'
    if activity in ('No record on selected date','No record in period'):frame=frame[frame.training_followup_eligible]
    if activity=='Done on selected date': frame=frame[frame[selected_date]]
    elif activity=='No record on selected date': frame=frame[~frame[selected_date]]
    elif activity=='Needs review': frame=frame[frame.needs_review]
    elif activity!='All': frame=frame[frame[consistency].eq(activity)]
    return frame.sort_values(['driver_name','driver_id'])


def daily_graph(frame,c,key):
    ids=set(frame.driver_id)
    events=c.report.events
    selected=events[events.driver_id.isin(ids) & events.inspection_date.isin(c.dates)]
    counts=selected.groupby('inspection_date').driver_id.nunique()
    data=pd.DataFrame({'date':c.dates,'drivers':[int(counts.get(d,0)) for d in c.dates]})
    st.markdown('**Drivers recording their own DVIR each day**')
    fig=px.line(data,x='date',y='drivers',markers=True,text='drivers',color_discrete_sequence=[GREEN],labels={'date':'','drivers':'Drivers with DVIR'})
    fig.update_traces(textposition='top center',cliponaxis=False,hovertemplate='%{x|%b %d}<br>%{y} drivers<extra></extra>')
    fig.update_xaxes(dtick='D1',tickformat='%b %d')
    fig.update_yaxes(range=[0,max(1,data.drivers.max())*1.2])
    show(fig,f'view-{key}-daily',height=290)
    st.caption('Each person counts once per date, even with several inspections. Partner activity stays separate.')


def heatmap(frame,c,key):
    st.subheader('Daily DVIR heatmap')
    if frame.empty:
        st.info('No drivers to display.');return
    st.caption('Read across a driver’s row to see each date. Numbers count that person’s own DVIRs.')
    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px">'
        '<span style="background:#d1fae5;color:#064e3b;padding:6px 12px;border-radius:6px">Recorded · DVIR count</span>'
        '<span style="background:#fef3c7;color:#78350f;padding:6px 12px;border-radius:6px">Recorded · review needed</span>'
        '<span style="background:#ede9fe;color:#4c1d95;padding:6px 12px;border-radius:6px">Day off · no DVIR</span>'
        '<span style="background:#dbeafe;color:#1e3a8a;padding:6px 12px;border-radius:6px">Before training / not trained</span>'
        '<span style="background:#eef2f6;color:#334155;padding:6px 12px;border-radius:6px">No DVIR recorded</span>'
        '</div>',unsafe_allow_html=True)
    pages=max(1,(len(frame)+19)//20)
    state=f'view-{key}-heatmap-page'
    signature=tuple(frame.driver_id)
    if st.session_state.get(state+'-signature')!=signature:
        st.session_state[state]=1;st.session_state[state+'-signature']=signature
    page=st.selectbox('Heatmap rows',range(1,pages+1),
        format_func=lambda n:f'Drivers {(n-1)*20+1}–{min(n*20,len(frame))} of {len(frame)} on this table page',
        key=state) if pages>1 else 1
    visible=frame.iloc[(page-1)*20:page*20]
    fig=calendar_figure(visible,c.report.events,c.dates)
    st.plotly_chart(fig,key=f'view-{key}-heatmap',width='stretch',
        config={'displaylogo':False,'scrollZoom':False,'modeBarButtonsToRemove':['select2d','lasso2d']})
    st.caption('Hover over a cell for the full date, driver, vehicles and status. Review means a recorded DVIR needs a data check. '
               'An asterisk (*) marks a DVIR on a day off. Days off and no-record cells do not establish a missed required inspection. Co-driver submissions stay on their own rows.')



def event_table(events,c,key):
    columns=['driver_name','driver_id','inspection_time','start_time','end_time','duration_minutes','source_block',
             'vehicle_names_in_report','trailer_ids_in_report','needs_review','source_row']
    table(display_times(events.sort_values('inspection_time',ascending=False),c.timezone),key,columns,size=50)
    st.caption('Vehicle/trailer inventories are supplied block context; their per-inspection date mapping is unavailable. No original Samsara DVIR IDs are supplied in this export.')


def overview():
    from .tracking_overview import render_tracking_overview
    c,summary=context_summary()
    st.title('Fleet overview')
    render_tracking_overview(c.report,c.end,table)
    with st.expander('Detailed driver analysis and heatmap',expanded=False):
        caption(c)
        roster=summary[summary.in_roster]
        metrics([('Roster drivers',len(roster)),('Solo with DVIR',int(roster.category.eq('Solo with DVIR').sum())),
                 ('Co-driver roster',int(roster.category.eq('Co-driver').sum())),('Solo without DVIR',int(roster.category.eq('Solo without DVIR').sum()))])
        st.caption('Each primary roster driver has exactly one source-based category: Co-driver first, then Solo with DVIR, then Solo without DVIR. Dates, status filters and graphs do not change that category. Partner detail is shown within the co-driver section.')
        st.page_link('pages/11_TruckMate_Roster.py',label=f'Open main TruckMate roster · {len(roster):,} drivers · {int((~roster.has_covered_DVIR & roster.training_followup_eligible).sum()):,} needing no-DVIR follow-up')
        partner_count=int(summary.loc[~summary.in_roster,'dated_PTIs'].sum())
        st.markdown(f'**{int(roster.dated_PTIs.sum()):,} roster-driver DVIRs** and **{partner_count:,} partner/unmatched DVIRs** in this period · **{len(c.report.events):,} inspection entries** in the complete uploaded file.')
        if roster.empty:
            st.info('This upload contains no TruckMate roster rows. View Data checks & unmatched for its DVIR authors.');return
        left,right=st.columns(2)
        with left:
            st.markdown('**DVIR consistency · own or co-driver submission**')
            counts=roster.coverage_consistency.value_counts().rename_axis('activity').reset_index(name='drivers')
            fig=px.bar(counts,x='drivers',y='activity',orientation='h',color='activity',
                       color_discrete_map={'Regular':GREEN,'Intermittent':YELLOW,'No record in period':GRAY})
            show(fig,'view-overview-consistency')
        with right:
            st.markdown('**Non-overlapping roster categories**')
            counts=roster.category.value_counts().rename_axis('category').reset_index(name='drivers')
            fig=px.pie(counts,names='category',values='drivers',hole=.65,color='category',
                       color_discrete_map={'Co-driver':BLUE,'Solo with DVIR':GREEN,'Solo without DVIR':GRAY})
            fig.update_traces(textinfo='label+value')
            show(fig,'view-overview-categories')
            st.caption(f'{int(roster.holiday_dates_in_period.gt(0).sum()):,} drivers have reported days off in this {len(c.dates)}-day period. Days off status is separate from category.')
        daily_graph(roster,c,'overview')
        left,right=st.columns(2)
        with left:
            st.markdown('**Highest own DVIR counts in the period**')
            top=roster[roster.dated_PTIs.gt(0)].sort_values('dated_PTIs',ascending=False).head(15).copy()
            if not top.empty:
                top['driver']=top.driver_name+' ('+top.driver_id+')'
                fig=px.bar(top,x='dated_PTIs',y='driver',orientation='h',color_discrete_sequence=[GREEN])
                fig.update_yaxes(autorange='reversed');show(fig,'view-overview-top',height=390)
            else: st.info('No dated DVIRs in this period.')
        with right:
            st.markdown('**Time since last own DVIR**')
            ages=roster.days_since_last
            labels=pd.Series('No own DVIR',index=roster.index)
            labels.loc[ages.between(0,2)]='0–2 days';labels.loc[ages.between(3,6)]='3–6 days';labels.loc[ages.ge(7)]='7+ days'
            counts=labels.value_counts().rename_axis('last_done').reset_index(name='drivers')
            show(px.bar(counts,x='drivers',y='last_done',orientation='h'),'view-overview-recency',height=390)
        st.caption(f'Regular = at least {(len(c.dates)+1)//2} of {len(c.dates)} recorded dates. Calendar gaps are follow-up information, not verified compliance misses.')
        left,right=st.columns(2)
        with left: st.page_link('pages/2_Driver_Consistency.py',label='Open solo drivers with DVIR')
        with right: st.page_link('pages/10_Without_DVIR.py',label='Open solo drivers without DVIR')
        st.subheader('Driver follow-up · solo and co-driver together')
        review_tab,compare_tab=st.tabs(['All roster drivers · DVIR coverage','Solo vs co-driver consistency'])
        with review_tab:
            st.caption('One row per primary roster driver. Own OR linked co-driver submissions count as coverage; neither submitting is the follow-up issue. Regular means at least 4 of 7 or 8 of 15 covered dates. Training is read only from this upload.')
            combined=filters(roster.copy(),c,'overview-roster',coverage=True)
            st.markdown(f'**{len(combined):,} matching drivers** · {int(combined.coverage_consistency.eq("Regular").sum()):,} regular · '
                        f'{int(combined.coverage_consistency.eq("Intermittent").sum()):,} intermittent · {int((combined.covered_dates_in_period.eq(0) & combined.training_followup_eligible).sum()):,} neither driver submitted in this period')
            visible=table(combined,'overview-roster',['dvir_coverage','coverage_consistency','covered_dates_in_period']+CORE,
                          sort_columns=('driver_name','dated_PTIs','recorded_dates','last_done'))
            heatmap(visible,c,'overview-roster')
        with compare_tab:
            compared=roster.assign(driver_group=roster.has_crew.map({True:'Co-driver',False:'Solo'}))
            counts=compared.groupby(['driver_group','coverage_consistency']).size().reset_index(name='drivers')
            fig=px.bar(counts,x='driver_group',y='drivers',color='coverage_consistency',text='drivers',barmode='stack',
                       color_discrete_map={'Regular':GREEN,'Intermittent':YELLOW,'No record in period':GRAY,'Needs date detail':BLUE},
                       labels={'driver_group':'Driver group','drivers':'Roster drivers','coverage_consistency':'Own or co-driver consistency'})
            show(fig,'view-overview-group-consistency',height=360)
            st.caption('Each primary roster driver counts once. Either co-driver submitting covers the roster driver. Actual own DVIR counts and source categories stay separate.')




def driver_list(kind):
    c,summary=context_summary()
    st.title('Solo drivers with DVIR' if kind=='with' else 'Solo drivers without DVIR');caption(c)
    frame=summary[summary.in_roster & summary.pti_training_status.eq('Done')].copy()
    st.caption('Only drivers with PTI training Done are shown here. Drivers with other training values remain in PTI training not done.')
    if kind=='with':
        frame=frame[frame.category.eq('Solo with DVIR')]
        st.caption('Source category: solo roster drivers with direct DVIR evidence in this upload. Co-driver records are in their own section. Use period/date filters to find recent recording or gaps without moving drivers between categories.')
    else:
        frame=frame[frame.category.eq('Solo without DVIR') & frame.training_followup_eligible]
        st.caption('Source category: solo roster drivers with no direct DVIR evidence in this upload. Crew-associated drivers stay in Co-driver teams, including those without an own submission.')
    frame=filters(frame,c,kind,arrangement_filter=False)
    metrics([('Drivers in list',len(frame)),('Own DVIRs in period',int(frame.dated_PTIs.sum())),
             ('Recorded on selected date',int(frame.on_selected_date.sum())),('Regular',int(frame.consistency.eq('Regular').sum()))])
    if not frame.empty: daily_graph(frame,c,kind)
    st.subheader('Driver list')
    visible=table(frame,f'{kind}-dvir-drivers',CORE,size=50,sort_columns=('driver_name','dated_PTIs','recorded_dates','last_done'))
    heatmap(visible,c,f'{kind}-drivers')
    st.caption('Vehicle/trailer counts labeled “file” cover the full uploaded history. Date counts and consistency use the selected period.')


def truckmate_roster():
    c,summary=context_summary();st.title('Main TruckMate driver roster');caption(c)
    roster=summary[summary.in_roster].copy()
    st.caption('Either the driver OR a linked co-driver submitting counts as covered. Follow-up is needed only when neither submitted. '
               'All TruckMate roster drivers are included; Samsara activation is a separate filter. Actual DVIR authors and own counts remain unchanged.')
    scope=st.radio('DVIR coverage',['All roster drivers','Own or co-driver DVIR present in upload',
                   'No own or co-driver DVIR anywhere in upload','No own or co-driver dated DVIR in selected period','Dates without DVIR or reported day off (period)'],key='view-roster-coverage-scope')
    frame=roster.copy()
    if scope=='Own or co-driver DVIR present in upload':frame=frame[frame.has_covered_DVIR]
    elif scope=='No own or co-driver DVIR anywhere in upload':frame=frame[~frame.has_covered_DVIR & frame.training_followup_eligible]
    elif scope=='No own or co-driver dated DVIR in selected period':frame=frame[frame.covered_dates_in_period.eq(0) & frame.training_followup_eligible]
    elif scope=='Dates without DVIR or reported day off (period)':frame=frame[frame.coverage_dates_without_recorded_holiday.gt(0)]
    metrics([('TruckMate roster',len(roster)),('Covered by own or co-driver DVIR',int(roster.has_covered_DVIR.sum())),
             ('No-DVIR follow-up (upload)',int((~roster.has_covered_DVIR & roster.training_followup_eligible).sum())),('No-DVIR follow-up (period)',int((roster.covered_dates_in_period.eq(0) & roster.training_followup_eligible).sum()))])
    st.caption('Days off status covers the full selected period: all dates, some dates, no reported dates, or unknown. The gap column excludes each driver’s reported dates off and dates covered by either co-driver. Unknown days-off data remains a prompt to check availability.')
    st.caption('No-DVIR follow-up excludes known untrained drivers and training on/after the report-ending date. During-period training starts the gap check the next day. Training dates and status remain visible in All roster drivers; missing dates stay explicitly unknown.')
    frame=filters(frame,c,'roster-no-dvir',coverage=True)
    st.markdown(f'**{len(frame):,} drivers match your filters**')
    visible=table(frame,'roster-no-dvir',['tms_id','dvir_coverage','coverage_consistency','covered_dates_in_period']+CORE,
                  sort_columns=('driver_name','covered_dates_in_period','dated_PTIs','last_done'))
    st.caption('The table above uses own-or-co-driver coverage. The heatmap below shows actual authors’ own submissions only; an empty own cell can still be covered by a partner.')
    heatmap(visible,c,'roster-no-dvir')



def co_drivers():
    c,summary=context_summary();st.title('Co-driver teams');caption(c)
    teams=crew_summary(c.report,c.dates,c.end)
    if teams.empty:
        st.info('No co-driver information was supplied in this file.');return
    co_roster=summary[summary.category.eq('Co-driver')]
    st.caption(f'{len(co_roster):,} primary roster drivers are classified here: {int(co_roster.has_own_DVIR.sum()):,} with own DVIR evidence and {int((~co_roster.has_own_DVIR).sum()):,} without own DVIR evidence. Both stay in this category.')
    own_tab,team_tab=st.tabs(['All co-drivers · own DVIR','Inspect by co-driver group'])
    with own_tab:
        st.subheader('Review every co-driver’s own submissions')
        st.caption('All linked members are listed once by driver ID, including partners outside the primary roster. A partner’s submission never counts as your own. Use filters and pages to review the full list.')
        st.caption('No-DVIR and training follow-up filters exclude the driver whenever either linked member submitted. Own counts and the heatmap below still show the actual author.')
        all_members=filters(summary[summary.has_crew].copy(),c,'co-own',arrangement_filter=False,coverage=True)
        metrics([('Drivers in list',len(all_members)),('Own DVIRs in period',int(all_members.dated_PTIs.sum())),
                 ('Regular coverage',int(all_members.coverage_consistency.eq('Regular').sum())),('No-DVIR follow-up in period',int((all_members.covered_dates_in_period.eq(0) & all_members.training_followup_eligible).sum()))])
        if not all_members.empty:daily_graph(all_members,c,'co-own')
        visible=table(all_members,'co-own-drivers',['dvir_coverage','coverage_consistency','covered_dates_in_period']+CORE+['in_roster'],sort_columns=('driver_name','dated_PTIs','recorded_dates','last_done'))
        heatmap(visible,c,'co-own')
    with team_tab:
        left,middle,right=st.columns([2,1,1])
        query=left.text_input('Search teams',placeholder='Driver, ID or vehicle',key='view-crew-search')
        account=middle.selectbox('Member Samsara status',['All','Active','Deactivated','Unknown'],key='view-crew-status')
        pattern=right.selectbox('Team PTI activity',['All','Done on selected date','No record on selected date','Regular','Intermittent','No record in period','Needs review'],key='view-crew-activity')
        if query.strip():
            mask=pd.Series(False,index=teams.index)
            for field in ('team_members','vehicle_names','unmapped_crew_members'):
                mask |= teams[field].fillna('').str.contains(query.strip(),case=False,regex=False)
            teams=teams[mask]
        coverage_filter=st.selectbox('Team DVIR in uploaded file',['All','Either member has DVIR','Neither member has DVIR'],key='view-crew-file-coverage')
        evidence_ids=set(summary.loc[summary.has_own_DVIR,'driver_id'])
        if coverage_filter=='Either member has DVIR':
            teams=teams[teams.members.map(lambda members:bool(members & evidence_ids))]
        eligible_ids=set(summary.loc[summary.training_followup_eligible,'driver_id'])
        primary_ids=set(summary.loc[summary.in_roster,'driver_id'])
        eligible_team=lambda members:bool((members & primary_ids or members) & eligible_ids)
        if coverage_filter=='Neither member has DVIR':
            teams=teams[teams.members.map(lambda members:not bool(members & evidence_ids) and eligible_team(members))]
        states=c.report.people.set_index('driver_id').samsara_status.to_dict()
        if account!='All': teams=teams[teams.members.map(lambda ids:any(states.get(key,'Unknown')==account for key in ids))]
        today=set(c.report.events.loc[c.report.events.inspection_date.eq(c.end),'driver_id'])
        if pattern in ('No record on selected date','No record in period'):teams=teams[teams.members.map(eligible_team)]
        if pattern=='Done on selected date': teams=teams[teams.members.map(lambda ids:bool(ids&today))]
        elif pattern=='No record on selected date': teams=teams[teams.members.map(lambda ids:not bool(ids&today))]
        elif pattern=='Needs review': teams=teams[teams.needs_review]
        elif pattern!='All': teams=teams[teams.consistency.eq(pattern)]
        metrics([('Teams',len(teams)),('Regular teams',int(teams.consistency.eq('Regular').sum())),
                 ('Intermittent teams',int(teams.consistency.eq('Intermittent').sum())),('No record in period',int(teams.consistency.eq('No record in period').sum()))])
        st.caption('Crew grouping uses vehicleName, cogoID/driverName slots and matched_on. Primary and CODRIVER blocks stay attached to their own IDs. '
                   'Combined regularity uses either member’s recorded dates; each person’s own activity remains visible.')
        columns=['team_members','vehicle_names','samsara_status','member_statuses','dated_PTIs','recorded_dates','consistency',
                 'each_person_own_PTIs','member_training','member_safety','reported_vehicle_count','reported_trailer_count','reported_totalPTI','last_done',
                 'known_duration_minutes','duration_records','unmapped_crew_members','multiple_crew_membership']
        table(display_times(teams,c.timezone),'co-driver-teams',columns,size=25,sort_columns=('team_members','dated_PTIs','recorded_dates','last_done'))
        st.caption('Source counts cover the uploaded file; dated counts cover the selected period. Do not sum across overlapping crews. Source crew membership is not verified for every historical inspection.')
        if teams.empty:return
        choices=teams.set_index('crew_id').team_members.to_dict();state='view-selected-crew'
        if st.session_state.get(state) not in choices: st.session_state[state]=next(iter(choices))
        selected=st.selectbox('Inspect a team',list(choices),format_func=choices.get,key=state)
        crew=teams.set_index('crew_id').loc[selected]
        members=summary[summary.driver_id.isin(crew.members)]
        st.subheader('Each person’s own activity')
        table(members,'team-member-activity',CORE,size=25)
        heatmap(members,c,'team-members')
        if crew.unmapped_crew_members: st.info('Additional crew member needs an ID match: '+crew.unmapped_crew_members)
        st.subheader('Team inspection records · author shown on every row')
        all_dates=st.checkbox('Show all uploaded inspection dates',key='view-team-all-dates')
        events=c.report.events[c.report.events.driver_id.isin(crew.members)]
        if not all_dates:events=events[events.inspection_date.isin(c.dates)]
        event_table(events,c,'team-inspection-records')


def individual():
    c,summary=context_summary();st.title('Individual driver');caption(c)
    requested=st.session_state.pop('view-profile-target',None)
    if requested in set(summary.driver_id):
        st.session_state['view-profile-role']='All'
        st.session_state['view-profile-search']=''
        st.session_state['view-profile-driver']=requested
    role=st.selectbox('Driver group',['All','Primary roster','Linked co-drivers','Unmatched DVIR authors'],key='view-profile-role')
    if role=='Primary roster':summary=summary[summary.in_roster]
    elif role=='Linked co-drivers':summary=summary[~summary.in_roster & summary.has_crew]
    elif role=='Unmatched DVIR authors':summary=summary[~summary.in_roster & ~summary.has_crew]
    query=st.text_input('Find a driver',placeholder='Name or ID',key='view-profile-search')
    if query.strip():summary=summary[summary.driver_name.str.contains(query.strip(),case=False,regex=False) | summary.driver_id.str.contains(query.strip(),case=False,regex=False)]
    if summary.empty:st.info('No drivers match.');return
    labels={r.driver_id:f'{r.driver_name} ({r.driver_id})' for r in summary.sort_values('driver_name').itertuples()}
    key='view-profile-driver'
    if st.session_state.get(key) not in labels:st.session_state[key]=next(iter(labels))
    selected=st.selectbox('Driver',list(labels),format_func=labels.get,key=key)
    frame=summary[summary.driver_id.eq(selected)];row=frame.iloc[0]
    st.subheader(row.driver_name)
    st.write(f'**{row.vehicle_names}** · {row.samsara_status} · {DAYS_OFF_STATUS.get(row.availability,row.availability)} · {row.arrangement}')
    st.caption(f'Safety status (uploaded file): {row.safety_status_file} · Supplied values: {row.safety_values_file}')
    metrics([('Own DVIRs in period',int(row.dated_PTIs)),('Recorded dates',int(row.recorded_dates)),
             ('Partner DVIRs in period',int(row.partner_PTIs_in_period)),('Dates without DVIR or reported day off',int(row.coverage_dates_without_recorded_holiday))])
    st.caption(f'Consistency: {row.consistency} · last own DVIR: {row.last_done if pd.notna(row.last_done) else "No matched record"}')
    heatmap(frame,c,'individual')
    tabs=st.tabs(['Own DVIR records','Missing / days off','Crew & driver information'])
    with tabs[0]:
        all_dates=st.checkbox('All inspection dates in this upload',value=True,key='view-person-all-dates')
        events=c.report.events[c.report.events.driver_id.eq(selected)]
        if not all_dates:events=events[events.inspection_date.isin(c.dates)]
        event_table(events,c,'individual-dvir-history')
    with tabs[1]:
        period=c.report.events[c.report.events.driver_id.eq(selected) & c.report.events.inspection_date.isin(c.dates)]
        known=set(period.inspection_date)
        calendar=pd.DataFrame([{'driver_name':row.driver_name,'driver_id':selected,'date':day,
                               'status':'Recorded' if day in known else 'Day off' if day in row.holidays else 'Not trained' if row.training_explicitly_incomplete else 'Before training' if row.training_completed_date is not None and day<row.training_completed_date else 'Training date' if day==row.training_completed_date else 'No own DVIR'} for day in c.dates])
        choice=st.selectbox('Calendar status',['All','Recorded','Day off','Before training','Training date','Not trained','No own DVIR'],key='view-person-calendar-filter')
        table(calendar if choice=='All' else calendar[calendar.status.eq(choice)],'individual-calendar',size=15)
    with tabs[2]:
        info=pd.DataFrame([{'field':field.replace('_',' ').title(),'value':str(row[field]) if row[field] is not None else 'Not supplied'}
                           for field in ('driver_id','tms_id','cogo_id','samsara_status','pti_training_status','pti_training_date','training_period_status','phone','license_number','state')])
        st.dataframe(info,hide_index=True,width='stretch')
        teams=crew_summary(c.report,c.dates,c.end)
        if not teams.empty:
            teams=teams[teams.members.map(lambda ids:selected in ids)]
            table(teams,'individual-source-crews',['team_members','vehicle_names','each_person_own_PTIs','unmapped_crew_members'],size=25)
        blocks=c.report.blocks[c.report.blocks.driver_id.eq(selected)]
        table(blocks,'individual-source-counts',['source_block','source_row','reported_vehicle_count','reported_trailer_count','reported_totalPTI','timestamp_pairs','vehicle_names','trailer_ids','counted_in_totals'],size=25)


def checks():
    c,summary=context_summary();st.title('Data checks & unmatched authors');caption(c)
    audit,unmatched=st.tabs(['Data checks','Authors outside primary roster'])
    with audit:
        issues=c.report.issues
        counts=issues.severity.value_counts() if not issues.empty else {}
        metrics([('Source rows',c.report.source_rows),('Inspection entries',len(c.report.events)),
                 ('Review items',int(counts.get('Review',0))),('Information',int(counts.get('Information',0)))])
        level=st.selectbox('Check type',['All','Review','Information'],key='view-check-type')
        table(issues if level=='All' else issues[issues.severity.eq(level)],'data-checks',size=50)
        st.caption('Review flags identify uncertainty; they do not automatically change a driver’s identity or prove a compliance failure.')
    with unmatched:
        frame=summary[~summary.in_roster].copy()
        frame['relationship']=frame.has_crew.map({True:'Linked co-driver outside primary roster',False:'Unmatched DVIR author · needs review'})
        frame=filters(frame,c,'unmatched')
        table(frame,'outside-roster-authors',CORE+['relationship'],size=50)
