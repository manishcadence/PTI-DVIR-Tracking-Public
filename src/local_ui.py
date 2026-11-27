"""The active app accepts uploads only. No API, SQLite, training store or file fallback."""
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import streamlit as st
from dotenv import load_dotenv, dotenv_values
from .upload_model import UploadReport, UploadError, parse_upload

ROOT=Path(__file__).resolve().parents[1]

@dataclass
class LocalContext:
    report: UploadReport
    dates: list
    end: object
    timezone: str
    filename: str


def clear_upload_state():
    for key in list(st.session_state):
        if key in ('upload_context','local-model','local-digest','local-report-end',
                   'local-upload-contents','local-upload-filename','local-saved-end') or key.startswith('view-'):
            st.session_state.pop(key,None)


def upload_changed(widget_key):
    # A user removing the file is different from a redirect temporarily losing
    # the widget value. Only an explicit removal clears the current session data.
    if st.session_state.get(widget_key) is None:
        clear_upload_state()


def prepare(fixed_days=None,tracking_overview=False):
    load_dotenv(ROOT/'.env')
    st.session_state.pop('context',None)  # Never reuse a legacy database-backed page context.
    sidebar=st.sidebar
    sidebar.title('Fleet DVIR')
    # Read this editable setting on each rerun, avoiding a stale dotenv value in the server process.
    download_url=dotenv_values(ROOT/'.env').get('PTI_DOWNLOAD_URL') or os.getenv('PTI_DOWNLOAD_URL')
    if not download_url:
        try:
            download_url=st.secrets.get('PTI_DOWNLOAD_URL')
        except FileNotFoundError:
            download_url=None
    sidebar.link_button('Get DVIR',download_url or '#',width='stretch',disabled=not bool(download_url),
                        help='Open n8n to download your JSON, then upload the file below.')
    if not download_url:
        sidebar.caption('Get DVIR is not configured. You can still upload a JSON file.')
    export_area=sidebar.container()
    sidebar.caption('Get DVIR → download the file → upload JSON here.')
    if sidebar.button('Clear uploaded data',key='local-clear-upload',width='stretch'):
        st.session_state['local-generation']=st.session_state.get('local-generation',0)+1
        clear_upload_state()
        st.rerun()
    generation=st.session_state.get('local-generation',0)
    widget_key=f'local-upload-{generation}'
    upload=sidebar.file_uploader('Upload DVIR JSON',type=['json'],key=widget_key,
                                 on_change=upload_changed,args=(widget_key,))
    contents=upload.getvalue() if upload is not None else st.session_state.get('local-upload-contents')
    name=getattr(upload,'name','Uploaded JSON') if upload is not None else st.session_state.get('local-upload-filename','Uploaded JSON')
    if contents is None:
        clear_upload_state()
        st.title('Upload your DVIR report')
        st.info('Use Get DVIR to download your file, then upload it in the sidebar. The dashboard starts empty.')
        st.caption('Data stays in this session. No database or saved reports are loaded.')
        st.stop()
    timezone=os.getenv('PTI_TIMEZONE','America/Chicago')
    try: ZoneInfo(timezone)
    except Exception:
        st.error('The configured timezone is invalid.');st.stop()
    digest=hashlib.sha256(contents+timezone.encode()+b'safety-status-file-v1').hexdigest()
    if st.session_state.get('local-digest')!=digest:
        st.session_state.pop('upload_context',None)
        st.session_state.pop('local-model',None)
        st.session_state.pop('local-upload-contents',None)
        st.session_state.pop('local-upload-filename',None)
        try: report=parse_upload(contents,timezone)
        except (UploadError,ValueError,TypeError,KeyError) as error:
            st.error(str(error));st.stop()
        if report.people.empty:
            st.info('No driver rows were found in this JSON.');st.stop()
        st.session_state['local-model']=report
        st.session_state['local-digest']=digest
        st.session_state.pop('local-report-end',None)
        st.session_state['local-saved-end']=report.latest
        for key in list(st.session_state):
            if key.startswith('view-'): st.session_state.pop(key,None)
    st.session_state['local-upload-contents']=contents
    st.session_state['local-upload-filename']=name
    report=st.session_state['local-model']
    sidebar.divider()
    if fixed_days is not None:
        days=fixed_days
        sidebar.caption(f'Reporting period: Last {days} days')
    else:
        if tracking_overview:
            sidebar.caption('Overview snapshot: always 15 days. The period below controls the detailed analysis and heatmap.')
        days=sidebar.radio('Reporting period',[7,15],format_func=lambda n:f'Last {n} days',horizontal=True,index=1 if st.session_state.get('local-saved-days')==15 else 0,key='local-days')
    saved_end=st.session_state.get('local-saved-end',report.latest)
    end=sidebar.date_input('Report ending',value=saved_end,min_value=report.earliest,max_value=report.latest,key='local-report-end')
    dates=[end-timedelta(days=i) for i in reversed(range(days))]
    if fixed_days is None:
        st.session_state['local-saved-days']=days
    st.session_state['local-saved-end']=end
    sidebar.caption(f'Current file: {name}')
    sidebar.caption(f'Latest inspection: {report.latest:%b %d, %Y} · {timezone}' if report.events.inspection_time.notna().any() else 'No usable inspection dates supplied.')
    sidebar.caption('Only this upload is used. Replacing or clearing it replaces the current data.')
    context=LocalContext(report,dates,end,timezone,name)
    st.session_state['upload_context']=context
    from .stakeholder_report import build_stakeholder_report, excel_bytes, REPORT_VERSION
    export_key=(digest,end,name,REPORT_VERSION)
    export_cache=st.session_state.get('view-sidebar-report-cache')
    if export_cache is None or export_cache[0]!=export_key:
        export_cache=(export_key,excel_bytes(build_stakeholder_report(report,end,name)))
        st.session_state['view-sidebar-report-cache']=export_cache
    export_area.download_button('Download Excel report (5 sheets)',export_cache[1],
        file_name=f'PTI_15_day_report_{end.isoformat()}.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        key='view-sidebar-report-download',width='stretch',on_click='ignore',type='primary')
    export_area.caption('15-day report · all five sheets · current upload')
    return context


def page_context():
    context=st.session_state.get('upload_context')
    if context is None:
        st.switch_page('app.py')
    return context
