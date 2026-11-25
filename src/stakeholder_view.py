"""Focused tables for sharing with supervisors and other stakeholders."""
import streamlit as st
from .local_ui import page_context
from .stakeholder_report import build_stakeholder_report, excel_bytes
from .components.tables import csv_bytes, display_frame


def stakeholder_view():
    context = page_context()
    st.title('Simple 15-day report')
    report = build_stakeholder_report(context.report, context.end, context.filename)
    st.caption(f'{report.start:%b %d, %Y} to {report.end:%b %d, %Y} · TruckMate roster · {context.filename}')
    st.write('Download the Excel report or select a table below. This report always uses 15 days, ending on the sidebar report date.')
    st.download_button('Download Excel report (5 sheets)', excel_bytes(report),
        file_name=f'PTI_15_day_report_{report.end.isoformat()}.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        key='view-stakeholder-excel', type='primary')
    st.caption('Solo tables and No PTI in entire file include only drivers with PTI training Done. Other drivers remain in PTI training not done. Co-driver tables keep the existing either-member submission rule; days off and training remain visible.')
    st.caption('Safety values cover the uploaded file, not a verified current condition or a specific inspection date. Missing values are Not supplied; grouped priority is Unsafe, Resolved, other non-safe values, then Safe.')
    query = st.text_input('Find a driver or vehicle', key='view-stakeholder-search')
    tabs = st.tabs(list(report.tables))
    for tab, (name, data) in zip(tabs, report.tables.items()):
        with tab:
            if query.strip():
                data = data[data.astype(str).apply(lambda col: col.str.contains(query.strip(), case=False, regex=False)).any(axis=1)]
            if name in ('No PTI in entire file','Solo without DVIR'):
                no_days=int(data['Days off category'].eq('No days off reported').sum())
                has_days=int(data['Days off category'].eq('Has days off').sum())
                st.markdown(f'**{no_days:,} no days off reported** · **{has_days:,} has days off**')
                days_off=st.selectbox('Days off follow-up',['All','No days off reported','Has days off'],
                    index=1 if name=='No PTI in entire file' else 0,key=f'view-stakeholder-days-off-{name}')
                if days_off!='All':data=data[data['Days off category'].eq(days_off)]
                st.caption('Days off uses the selected 15-day count: above zero means Has days off; zero or Not supplied is grouped as No days off reported. The original count stays visible.')
            if name=='Solo without DVIR':
                history=st.selectbox('DVIR history',['All','No record in entire file','Has records in file'],
                    key='view-stakeholder-solo-history')
                if history!='All':data=data[data['DVIR history'].eq(history)]
                st.caption('Has records in file means inspection evidence exists in the upload, but no dated DVIR is in this selected 15-day period. Undated evidence remains marked for date review.')
            st.write(f'**{len(data):,} rows**')
            if name == 'No PTI in entire file':
                st.caption('TruckMate roster drivers with PTI training Done and no own or linked co-driver PTI evidence anywhere in this upload. Older DVIRs or positive undated inspection counts exclude a driver from this sheet. This does not claim lifetime history.')
            elif name == 'Solo without DVIR':
                st.caption('Solo roster drivers with PTI training Done and no dated DVIR in these 15 days. Read Status for days off, training dates or missing-date exceptions.')
            elif name.startswith('Co-driver '):
                st.caption(f'{report.co_roster_count:,} TruckMate roster drivers have crew information. Each row is a supplied group; both names and each member’s own DVIR counts are shown. Overlapping groups should not be summed.')
            st.download_button('Download this table (CSV)', csv_bytes(data),
                file_name=f'{name.replace(" ","_")}_{report.end.isoformat()}.csv', mime='text/csv',
                key=f'view-stakeholder-csv-{name}')
            if name in ('No PTI in entire file','Solo without DVIR'):
                st.caption('CSV follows the selected filters. The five-sheet Excel report includes all groups and their category columns.')
            if data.empty:
                st.info('No matching drivers.')
            else:
                st.dataframe(display_frame(data, text_columns=('Days off',)), hide_index=True, width='stretch', height=min(650, 42*len(data)+40))
