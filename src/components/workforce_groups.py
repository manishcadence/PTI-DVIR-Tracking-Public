"""Account-status-first solo, team and unmatched-author lists."""
import pandas as pd
import streamlit as st
from ..workforce import account_statuses, team_summary, source_totals, review_drivers, distinct_activity
from .tables import table, csv_bytes, display_times


def workforce_filters(summary,data,dates,timezone='America/Chicago'):
    matched=summary[summary.in_roster].copy()
    counts=matched.samsara_status.value_counts()
    for label,color in [('Active','green'),('Deactivated','red'),('Unknown','gray')]:
        st.badge(f'{label} · {int(counts.get(label,0)):,}',color=color)
    left,right=st.columns(2)
    status=left.radio('Samsara account status',['All','Active','Deactivated','Unknown'],index=1 if counts.get('Active',0) else 0,horizontal=True,key='workforce-account-status')
    arrangement=right.radio('Driver arrangement',['All','Solo','Co-driver'],horizontal=True,key='workforce-arrangement')
    pattern=st.selectbox('DVIR submission pattern',['All','Regular','Intermittent','No matched DVIR','Needs individual DVIR detail'],key='workforce-pattern')
    if status!='All': matched=matched[matched.samsara_status.eq(status)]
    if arrangement!='All': matched=matched[matched.driver_mode.eq(arrangement)]
    if pattern!='All':
        if arrangement=='Co-driver':
            teams=team_summary(data,dates,timezone)
            wanted='No recorded dates' if pattern=='No matched DVIR' else pattern
            teams=teams[teams.needs_individual_DVIR_detail] if pattern=='Needs individual DVIR detail' else teams[teams.team_consistency.eq(wanted)]
            eligible={key for text in teams.member_ids for key in text.split(', ')}
            matched=matched[matched.driver_id.isin(eligible)]
        else:
            matched=matched[matched.consistency.eq(pattern)]
    st.caption('Account status comes from SamsaraStatus: active / deactive. Holiday availability and submission consistency are separate. Solo means no partner information was supplied. With Co-driver selected, submission pattern uses combined team dates; individual counts stay separate.')
    return matched,status,arrangement,pattern


def solo_totals(data,summary):
    output=[]
    for row in summary.to_dict('records'):
        sources=[source for source in data.source_rows if source.get('_dvir_author_id')==row['driver_id'] or (source.get('_roster_driver_id')==row['driver_id'] and not source.get('_dvir_author_id'))]
        output.append({**row,**source_totals(sources)})
    return pd.DataFrame(output)


def render_teams(context,dates,status='All',eligible_ids=None,pattern='All'):
    st.subheader('Co-driver teams · combined PTI activity')
    teams=team_summary(context.data,dates,context.timezone)
    if eligible_ids is not None and not teams.empty:
        teams=teams[teams.member_ids.map(lambda text: bool(set(text.split(', ')) & set(eligible_ids)))]
    if status!='All' and not teams.empty:
        field={'Active':'has_active_member','Deactivated':'has_deactivated_member','Unknown':'has_unknown_member'}[status]
        teams=teams[teams[field]]
    if pattern!='All' and not teams.empty:
        translated={'No matched DVIR':'No recorded dates','Needs individual DVIR detail':None}.get(pattern,pattern)
        teams=teams[teams.needs_individual_DVIR_detail] if translated is None else teams[teams.team_consistency.eq(translated)]
    st.caption('Both drivers’ activity is combined once per authored timestamp record. Each person’s own count remains visible. '
               'Mixed-status teams show each member’s status; the selected status matches any member. Current source crew does not verify historical team timing.')
    st.caption('Reported vehicle/trailer/totalPTI counts cover the full uploaded file. Dated counts and regularity use the selected 7/15 dates. '
               'Do not sum across team rows when a member appears in several crews.')
    st.download_button('Download complete team report CSV',csv_bytes(teams),'co-driver-team-report.csv',mime='text/csv',key='workforce-team-csv')
    visible=['team_members','member_ids','vehicle_names','samsara_status','member_statuses','combined_dated_PTIs',
             'combined_recorded_dates','dated_count_basis','team_consistency','each_driver_own_PTIs','each_driver_consistency','source_vehicle_count_full_file',
             'source_trailer_count_full_file','source_totalPTI_full_file','source_combined_equipment_count_full_file',
             'first_PTI_in_window','last_PTI_in_window','known_duration_minutes','duration_records',
             'multi_author_aggregate','needs_individual_DVIR_detail','needs_member_mapping','member_in_multiple_crews','source_count_note']
    table(teams.reindex(columns=visible),'workforce-team-summary',size=25,export=False)
    if not teams.empty:
        labels=teams.set_index('crew_id').team_members.to_dict()
        selected=st.selectbox('Team inspection detail',list(labels),format_func=lambda key:labels[key],key='workforce-crew-detail')
        members=set(teams.set_index('crew_id').loc[selected,'member_ids'].split(', '))
        records=distinct_activity(context.data)
        records=records[records.author_id.isin(members) & records.inspection_date.isin(dates)]
        st.caption('Each row below remains credited to its author. Blank duration/count fields mean unavailable information, not zero.')
        table(display_times(records[['dvir_id','author_id','author_name','inspection_time','start_time','end_time',
                                     'vehicle_name','vehicle_id','trailer_id','safety_status']],context.timezone),
              'workforce-team-inspections',size=25)


def render_review(context,dates,status='All'):
    st.subheader('Needs review · DVIR authors not matched to TruckMate/Monday')
    rows=review_drivers(context.data,dates)
    if status!='All': rows=rows[rows.samsara_status.eq(status)]
    mode=st.selectbox('Review driver arrangement',['All','Solo','Co-driver'],key='workforce-review-mode')
    if mode!='All': rows=rows[rows.driver_mode.eq(mode)]
    query=st.text_input('Search review drivers',placeholder='Name, Samsara ID or vehicle',key='workforce-review-search')
    if query.strip():
        mask=pd.Series(False,index=rows.index)
        for column in ('driver_name','driver_id','vehicle_names'):
            mask |= rows[column].fillna('').astype(str).str.contains(query.strip(),case=False,regex=False)
        rows=rows[mask]
    st.badge(f'Needs review · {len(rows):,}',color='orange')
    st.caption('These drivers are kept outside the matched roster, even if Samsara marks them active. '
               'Their DVIRs are retained. Unknown means no unambiguous SamsaraStatus for that exact author ID.')
    table(display_times(rows.assign(last_done=pd.to_datetime(rows.last_done,utc=True,errors='coerce')),context.timezone),
          'workforce-unmatched-review',size=25)
    if not rows.empty:
        all_review_ids=set(review_drivers(context.data,dates).driver_id)
        crews=team_summary(context.data,dates,context.timezone)
        if not crews.empty:
            crews=crews[crews.member_ids.map(lambda text:bool(set(text.split(', ')) & set(rows.driver_id)) and set(text.split(', ')).issubset(all_review_ids))]
            if not crews.empty:
                st.markdown('**Unmatched co-driver teams · needs review**')
                crews=crews.assign(review_tag='Needs review — unmatched team')
                table(crews,'workforce-review-teams',size=25)
        labels=rows.set_index('driver_id').driver_name.to_dict()
        driver=st.selectbox('Review driver DVIR history',list(labels),format_func=lambda key:f'{labels[key]} ({key})',key='workforce-review-driver')
        own=context.data.dvir_records[context.data.dvir_records.author_id.eq(driver)]
        table(display_times(own[['dvir_id','author_id','author_name','inspection_time','start_time','end_time',
                                'vehicle_name','vehicle_id','trailer_id','safety_status']],context.timezone),
              'workforce-review-inspections',size=25)
