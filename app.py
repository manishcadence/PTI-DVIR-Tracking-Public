"""Fleet DVIR dashboard: local uploads only, session memory only."""
import streamlit as st
from src.local_ui import prepare

st.set_page_config(page_title='Fleet DVIR',page_icon='🚚',layout='wide')
main_pages=[
    st.Page('pages/12_Simple_Report.py',title='Simple 15-day report'),
    st.Page('pages/13_PTI_Training.py',title='PTI training not done'),
    st.Page('pages/1_Fleet_Overview.py',title='Overview',default=True),
]
backend_pages=[
    st.Page('pages/2_Driver_Consistency.py',title='Solo with DVIR'),
    st.Page('pages/10_Without_DVIR.py',title='Solo without DVIR'),
    st.Page('pages/11_TruckMate_Roster.py',title='Main TruckMate roster'),
    st.Page('pages/4_Co_Driver_Analysis.py',title='Co-driver teams'),
    st.Page('pages/3_Driver_Profiles.py',title='Individual driver'),
    st.Page('pages/9_Unmatched_Review.py',title='Data checks & unmatched'),
]
navigation=st.navigation(main_pages+backend_pages,position='hidden')
with st.sidebar:
    for page in main_pages:
        st.page_link(page)
    with st.expander('Backend',expanded=navigation.title in {page.title for page in backend_pages}):
        for page in backend_pages:
            st.page_link(page)
prepare(fixed_days=15 if navigation.title=='Simple 15-day report' else None,
        tracking_overview=navigation.title=='Overview')
# Process selection callbacks after navigation has registered all pages.
if st.session_state.pop('view-profile-open',False):
    st.switch_page('pages/3_Driver_Profiles.py')
navigation.run()
