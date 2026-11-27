"""Current upload-only navigation and session behavior."""
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from test_upload_model import rows

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(autouse=True)
def navigation_mode(monkeypatch):
    from streamlit.runtime import pages_manager
    class TestPath(type(Path())):
        def exists(self):return False if self==ROOT/'pages' else super().exists()
    monkeypatch.setattr(pages_manager,'Path',TestPath)


def app():return AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)


def upload_mock(data=None):
    uploaded=BytesIO(json.dumps(rows() if data is None else data).encode())
    return patch('streamlit.delta_generator.DeltaGenerator.file_uploader',side_effect=lambda label,**kwargs:uploaded if label=='Upload DVIR JSON' else None)


@pytest.mark.parametrize('private_url',[None,'https://example.invalid/download'])
def test_download_url_uses_private_configuration_without_a_public_fallback(monkeypatch,private_url):
    monkeypatch.delenv('PTI_DOWNLOAD_URL',raising=False)
    secrets={'PTI_DOWNLOAD_URL':private_url} if private_url else {}
    with patch('src.local_ui.load_dotenv'),patch('src.local_ui.dotenv_values',return_value={}),patch('src.local_ui.st.secrets',secrets):
        dashboard=app().run()
        assert not dashboard.exception
        link=next(item for item in dashboard.get('link_button') if item.proto.label=='Get DVIR')
        assert link.proto.disabled is (private_url is None)
        assert link.proto.url==(private_url or '#')
        assert dashboard.file_uploader


def test_empty_start_ignores_all_old_source_and_database_settings(monkeypatch,tmp_path):
    monkeypatch.setenv('PTI_MODE','live');monkeypatch.setenv('PTI_UPLOAD_ONLY','false')
    monkeypatch.setenv('PTI_LOCAL_JSON_PATH','sample_data/grouped_driver_report.json')
    monkeypatch.setenv('PTI_HISTORY_DB',str(tmp_path/'must-not-exist.sqlite3'))
    with patch('sqlite3.connect',side_effect=AssertionError('Database must not be used')),patch('requests.Session.get') as get:
        dashboard=app().run()
        assert not dashboard.exception
        assert not dashboard.metric and not dashboard.dataframe
        assert 'Upload your DVIR report' in [item.value for item in dashboard.title]
        assert not get.called and not (tmp_path/'must-not-exist.sqlite3').exists()
        labels=[button.label for button in dashboard.sidebar.button]
        assert not any('reload' in label.lower() or 'refresh' in label.lower() for label in labels)
        assert any(link.proto.label=='Get DVIR' for link in dashboard.get('link_button'))
        assert not any('training' in item.value.lower() for item in dashboard.subheader)


def test_uploaded_file_loads_without_sqlite_or_network_and_navigates():
    with upload_mock(),patch('sqlite3.connect',side_effect=AssertionError('No database')),patch('requests.Session.get') as get:
        dashboard=app().run()
        assert not dashboard.exception
        assert [m.value for m in dashboard.metric if m.label in ('Roster drivers','Solo with DVIR','Co-driver roster','Solo without DVIR')]==['3','1','1','1']
        for file in ['2_Driver_Consistency.py','10_Without_DVIR.py','4_Co_Driver_Analysis.py','3_Driver_Profiles.py','9_Unmatched_Review.py','1_Fleet_Overview.py']:
            dashboard.switch_page('pages/'+file).run()
            assert not dashboard.exception
        assert not get.called


def test_without_dvir_keeps_driver_and_holiday_heatmap():
    data=rows();data[2]['PTITraining']='DONE'
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/10_Without_DVIR.py').run()
        assert not dashboard.exception
        frame=dashboard.dataframe[0].value
        assert frame['Driver ID'].tolist()==['D']
        assert frame['Days off status (period)'].tolist()==['Some days off']
        assert dashboard.get('plotly_chart')


def test_codriver_primary_and_partner_counts_are_separate():
    with upload_mock():
        dashboard=app().run().switch_page('pages/4_Co_Driver_Analysis.py').run()
        assert not dashboard.exception
        teams=next(item.value for item in dashboard.dataframe if 'Team Members' in item.value.columns)
        assert teams['DVIRs in period'].tolist()==[3]
        member=dashboard.dataframe[0].value.set_index('Driver ID')
        assert member.loc['A','DVIRs in period']==2 and member.loc['B','DVIRs in period']==1
        next(item for item in dashboard.selectbox if item.label=='Team PTI activity').set_value('Regular').run()
        assert not dashboard.exception
        assert any('No records match' in item.value for item in dashboard.info)


def test_filters_for_done_missing_and_account_status():
    data=rows();data[1]['PTITraining']='DONE'
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/2_Driver_Consistency.py').run()
        next(item for item in dashboard.selectbox if item.label=='PTI activity').set_value('Done on selected date').run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['C']
        next(item for item in dashboard.selectbox if item.label=='Samsara status').set_value('Deactivated').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['C']


def test_individual_driver_has_own_history_and_missing_dates():
    with upload_mock():
        dashboard=app().run().switch_page('pages/3_Driver_Profiles.py').run()
        next(item for item in dashboard.selectbox if item.label=='Driver').set_value('A').run()
        assert not dashboard.exception
        history=dashboard.dataframe[0].value
        assert set(history['Driver ID'])=={'A'} and len(history)==2
        calendar=next(frame.value for frame in dashboard.dataframe if 'Status' in frame.value.columns)
        assert len(calendar)==7
        assert set(calendar.Status)=={'Recorded','No own DVIR'}


def test_replacing_upload_replaces_session_dataset():
    value=BytesIO(json.dumps(rows()).encode())
    with patch('streamlit.delta_generator.DeltaGenerator.file_uploader',side_effect=lambda label,**kwargs:value if label=='Upload DVIR JSON' else None):
        dashboard=app().run()
        value=BytesIO(json.dumps([rows()[2]]).encode());dashboard.run()
        assert not dashboard.exception
        assert [m.value for m in dashboard.metric if m.label in ('Roster drivers','Solo with DVIR','Co-driver roster','Solo without DVIR')]==['1','0','0','1']
        assert dashboard.session_state['upload_context'].report.events.empty


def test_clear_upload_returns_to_empty_screen():
    value=BytesIO(json.dumps(rows()).encode())
    with patch('streamlit.delta_generator.DeltaGenerator.file_uploader',side_effect=lambda label,**kwargs:value if kwargs.get('key')=='local-upload-0' else None):
        dashboard=app().run()
        next(button for button in dashboard.button if button.key=='local-clear-upload').click().run()
        assert not dashboard.exception and not dashboard.metric and not dashboard.dataframe
        assert 'Upload your DVIR report' in [item.value for item in dashboard.title]


def test_invalid_upload_cannot_show_previous_data():
    value=BytesIO(json.dumps(rows()).encode())
    with patch('streamlit.delta_generator.DeltaGenerator.file_uploader',side_effect=lambda label,**kwargs:value if label=='Upload DVIR JSON' else None):
        dashboard=app().run();value=BytesIO(b'broken');dashboard.run()
        assert not dashboard.exception and dashboard.error
        assert not dashboard.metric and not dashboard.dataframe



def test_900_driver_table_sorts_globally_and_paginates_heatmap():
    data=[{'Tms_ID':f'T{i:04}','Samsara_DriverID':f'D{i:04}','Samsara_DriverName':f'Driver {i:04}',
           'totalPTI':None,'CODRIVER_totalPTI':None,'PTITraining':'DONE'} for i in range(900)]
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/10_Without_DVIR.py').run()
        assert not dashboard.exception
        assert len(dashboard.dataframe[0].value)==50
        next(item for item in dashboard.toggle if item.label=='Descending').set_value(True).run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].iloc[0]=='D0899'
        page=next(item for item in dashboard.selectbox if item.label.startswith('Page ·'))
        page.set_value(2).run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].iloc[0]=='D0849'
        assert dashboard.get('plotly_chart')



def test_navigation_categories_never_share_a_primary_driver():
    data=rows();data[1]['PTITraining']='DONE';data[2]['PTITraining']='DONE'
    with upload_mock(data):
        dashboard=app().run()
        assert [m.value for m in dashboard.metric if m.label in ('Roster drivers','Solo with DVIR','Co-driver roster','Solo without DVIR')]==['3','1','1','1']
        dashboard.switch_page('pages/2_Driver_Consistency.py').run()
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'C'}
        dashboard.switch_page('pages/10_Without_DVIR.py').run()
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'D'}
        assert not any(item.label=='Missing record scope' for item in dashboard.radio)
        dashboard.switch_page('pages/4_Co_Driver_Analysis.py').run()
        members=dashboard.dataframe[0].value
        assert set(members['Driver ID'])=={'A','B'}
        assert members.set_index('Driver ID').loc['A','Category']=='Co-driver'


def test_co_driver_without_own_dvir_stays_in_co_section_not_solo_without():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None);data[2]['PTITraining']='DONE'
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/10_Without_DVIR.py').run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        dashboard.switch_page('pages/4_Co_Driver_Analysis.py').run()
        next(item for item in dashboard.selectbox if item.label=='Team DVIR in uploaded file').set_value('Neither member has DVIR').run()
        assert not any('Team Members' in item.value.columns for item in dashboard.dataframe)
        next(item for item in dashboard.selectbox if item.label=='Team DVIR in uploaded file').set_value('All').run()
        assert not dashboard.exception
        assert len(next(item.value for item in dashboard.dataframe if 'Team Members' in item.value.columns))==1
        members=dashboard.dataframe[0].value.set_index('Driver ID')
        assert members.loc['A','DVIRs in period']==0
        assert members.loc['B','DVIRs in period']==1


def test_heatmap_can_show_all_drivers_on_current_table_page():
    data=[{'Tms_ID':f'T{i:04}','Samsara_DriverID':f'D{i:04}','Samsara_DriverName':f'Driver {i:04}',
           'totalPTI':None,'CODRIVER_totalPTI':None,'PTITraining':'DONE'} for i in range(50)]
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/10_Without_DVIR.py').run()
        control=next(item for item in dashboard.selectbox if item.label=='Heatmap rows')
        assert len(control.options)==3
        control.set_value(3).run()
        assert not dashboard.exception
        chart=next(item for item in dashboard.get('plotly_chart') if 'heatmap' in item.proto.id)
        spec=json.loads(chart.proto.spec)
        assert len(spec['data'][0]['y'])==10
        assert 'D0040' in spec['layout']['yaxis']['ticktext'][0]


def test_co_driver_own_view_lists_all_members_and_has_separate_team_tab():
    with upload_mock():
        dashboard=app().run().switch_page('pages/4_Co_Driver_Analysis.py').run()
        assert not dashboard.exception
        assert [tab.label for tab in dashboard.tabs]==['All co-drivers · own DVIR','Inspect by co-driver group']
        members=dashboard.dataframe[0].value.set_index('Driver ID')
        assert set(members.index)=={'A','B'}
        assert members.loc['A','PTI training']=='Done'
        assert members.loc['B','PTI training']=='Not done'
        assert len([chart for chart in dashboard.get('plotly_chart') if 'heatmap' in chart.proto.id])==2


def test_overview_both_training_followup_filters_include_solo_and_codrivers():
    data=rows()
    data[0]['PTITraining']='DONE'
    data[0]['appended_startTIme']=['2026-10-01T12:00:00Z']
    data[0]['appended_endTime']=['2026-10-01T12:05:00Z']
    data[2]['PTITraining']='DONE' # No own DVIR evidence anywhere.
    with upload_mock(data):
        dashboard=app().run()
        followup=next(item for item in dashboard.selectbox if item.label=='Training / DVIR follow-up')
        followup.set_value('Training done · no DVIR in file').run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        followup=next(item for item in dashboard.selectbox if item.label=='Training / DVIR follow-up')
        followup.set_value('Training done · no DVIR in period').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        next(item for item in dashboard.selectbox if item.label=='Training / DVIR follow-up').set_value('All').run()
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'A','C','D'}
        assert len(dashboard.get('plotly_chart'))>=7


def test_roster_followup_excludes_primary_when_partner_submitted():
    data=rows()
    data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None)
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        assert not dashboard.exception
        frame=dashboard.dataframe[0].value.set_index('Driver ID')
        assert set(frame.index)=={'A','C','D'}
        assert set(frame['TruckMate / TMW ID'])=={'TA','TC','TD'}
        assert frame.loc['A','Category']=='Co-driver'
        assert frame.loc['A','DVIR coverage (own or co-driver)']=='Co-driver DVIR'
        assert frame.loc['A','DVIRs in period']==0
        assert frame.loc['A','Partner DVIRs in period']==1
        assert [item.value for item in dashboard.metric]==['3','2','1','1']
        next(item for item in dashboard.radio if item.label=='DVIR coverage').set_value('No own or co-driver DVIR anywhere in upload').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        next(item for item in dashboard.selectbox if item.label=='Samsara status').set_value('Active').run()
        assert not dashboard.exception
        assert any('No records match' in item.value for item in dashboard.info)


def test_roster_missing_period_scope_includes_older_dvir_without_changing_category():
    data=rows()
    data[1]['appended_startTIme']=['2026-10-01T12:00:00Z']
    data[1]['appended_endTime']=['2026-10-01T12:05:00Z']
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        next(item for item in dashboard.radio if item.label=='DVIR coverage').set_value('No own or co-driver DVIR anywhere in upload').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        next(item for item in dashboard.radio if item.label=='DVIR coverage').set_value('No own or co-driver dated DVIR in selected period').run()
        assert not dashboard.exception
        frame=dashboard.dataframe[0].value.set_index('Driver ID')
        assert set(frame.index)=={'C','D'}
        assert frame.loc['C','Category']=='Solo with DVIR'
        next(item for item in dashboard.selectbox if item.label=='Samsara status').set_value('Deactivated').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['C']


def test_period_holiday_filter_and_gap_filter_exclude_full_holiday_driver():
    from datetime import date,timedelta
    data=rows();data[2]['appended_status_date']=[(date(2026,11,23)-timedelta(days=i)).isoformat() for i in range(7)];data[2]['count_status_date']=7
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        next(item for item in dashboard.selectbox if item.label=='Days off status (period)').set_value('On holiday all period').run()
        assert not dashboard.exception
        frame=dashboard.dataframe[0].value
        assert frame['Driver ID'].tolist()==['D']
        assert frame['Days off in period'].tolist()==[7]
        assert frame['Dates without DVIR or reported day off'].tolist()==[0]
        next(item for item in dashboard.selectbox if item.label=='Days off status (period)').set_value('All').run()
        next(item for item in dashboard.radio if item.label=='DVIR coverage').set_value('Dates without DVIR or reported day off (period)').run()
        assert not dashboard.exception
        assert 'D' not in set(dashboard.dataframe[0].value['Driver ID'])


def test_codriver_missing_period_and_file_filters_exclude_both_when_one_submits():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None)
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/4_Co_Driver_Analysis.py').run()
        next(item for item in dashboard.selectbox if item.key=='view-co-own-activity').set_value('No record in period').run()
        assert not dashboard.exception
        assert not any('In Roster' in item.value.columns for item in dashboard.dataframe)
        next(item for item in dashboard.selectbox if item.key=='view-crew-file-coverage').set_value('Neither member has DVIR').run()
        assert not any('Team Members' in item.value.columns for item in dashboard.dataframe)
        next(item for item in dashboard.selectbox if item.key=='view-co-own-activity').set_value('No record on selected date').run()
        assert not any('In Roster' in item.value.columns for item in dashboard.dataframe)


def test_codriver_no_dvir_filters_include_team_only_when_neither_submitted():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None,
                             CODRIVER_totalPTI=None,CODRIVER_count_vehicleID=None,CODRIVER_count_trailerID=None,
                             CODRIVER_appended_startTIme=None,CODRIVER_appended_endTime=None)
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/4_Co_Driver_Analysis.py').run()
        next(item for item in dashboard.selectbox if item.key=='view-co-own-activity').set_value('No record in period').run()
        next(item for item in dashboard.selectbox if item.key=='view-crew-file-coverage').set_value('Neither member has DVIR').run()
        assert not dashboard.exception
        members=next(item.value for item in dashboard.dataframe if 'In Roster' in item.value.columns)
        assert set(members['Driver ID'])=={'A','B'}
        teams=next(item.value for item in dashboard.dataframe if 'Team Members' in item.value.columns)
        assert len(teams)==1 and teams['DVIRs in period'].iloc[0]==0


def test_training_after_period_remains_visible_but_is_excluded_from_no_dvir_lists():
    data=rows();data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-24')
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        assert not dashboard.exception
        frame=dashboard.dataframe[0].value.set_index('Driver ID')
        assert frame.loc['D','Training relative to report']=='Trained after period'
        assert frame.loc['D','Training date (uploaded)']=='2026-11-24'
        next(item for item in dashboard.radio if item.label=='DVIR coverage').set_value('No own or co-driver dated DVIR in selected period').run()
        assert not dashboard.exception
        assert not dashboard.dataframe
        next(item for item in dashboard.radio if item.label=='DVIR coverage').set_value('No own or co-driver DVIR anywhere in upload').run()
        assert not dashboard.dataframe
        dashboard.switch_page('pages/1_Fleet_Overview.py').run()
        next(item for item in dashboard.selectbox if item.key=='view-overview-roster-training-followup').set_value('Training done · no DVIR in period').run()
        assert not dashboard.exception
        assert not dashboard.dataframe


def test_individual_calendar_marks_before_training_instead_of_missing_dvir():
    data=rows();data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-24')
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/3_Driver_Profiles.py').run()
        next(item for item in dashboard.selectbox if item.label=='Driver').set_value('D').run()
        assert not dashboard.exception
        calendar=next(item.value for item in dashboard.dataframe if 'Status' in item.value.columns)
        assert set(calendar.Status)=={'Before training','Day off'}


@pytest.mark.parametrize('page',['pages/11_TruckMate_Roster.py','pages/1_Fleet_Overview.py'])
def test_training_relative_filter_updates_with_reporting_window(page):
    data=rows();data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-12')
    with upload_mock(data):
        dashboard=app().run().switch_page(page).run()
        next(item for item in dashboard.selectbox if item.label=='Training relative to report').set_value('Trained before period').run()
        assert not dashboard.exception
        assert 'D' in set(dashboard.dataframe[0].value['Driver ID'])
        next(item for item in dashboard.radio if item.label=='Reporting period').set_value(15).run()
        assert not dashboard.exception
        assert 'D' not in set(dashboard.dataframe[0].value['Driver ID'])
        next(item for item in dashboard.selectbox if item.label=='Training relative to report').set_value('Trained during period').run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        next(item for item in dashboard.selectbox if item.label=='Training relative to report').set_value('All').run()
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'A','C','D'}


def test_driver_cell_navigation_uses_rendered_ids_and_ignores_other_columns(monkeypatch):
    from src import local_views
    state={'driver-table':{'selection':{'cells':[(1,'Driver')]}}}
    monkeypatch.setattr(local_views.st,'session_state',state)
    with patch.object(local_views.st,'switch_page') as navigate:
        local_views.open_selected_driver('driver-table',('B','A'))
        assert state['view-profile-target']=='A'
        assert state['view-profile-open'] is True
        navigate.assert_not_called()
        state.pop('view-profile-open')
        state['driver-table']['selection']['cells']=[(0,'DVIRs in period')]
        local_views.open_selected_driver('driver-table',('B','A'))
        navigate.assert_not_called()
        assert 'view-profile-open' not in state
        state['driver-table']['selection']['cells']=[(9,'Profile')]
        local_views.open_selected_driver('driver-table',('B','A'))
        navigate.assert_not_called()


def test_profile_navigation_clears_stale_filters_and_opens_exact_same_name_driver():
    data=rows();data[0]['Samsara_DriverName']='Same name';data[0]['CODRIVER_driverName']='Same name'
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/3_Driver_Profiles.py').run()
        next(item for item in dashboard.selectbox if item.label=='Driver group').set_value('Primary roster').run()
        next(item for item in dashboard.text_input if item.label=='Find a driver').set_value('missing name').run()
        dashboard.session_state['view-profile-target']='B'
        dashboard.run()
        assert not dashboard.exception
        assert next(item for item in dashboard.selectbox if item.label=='Driver').value=='B'
        assert next(item for item in dashboard.selectbox if item.label=='Driver group').value=='All'
        assert next(item for item in dashboard.text_input if item.label=='Find a driver').value==''
        history=dashboard.dataframe[0].value
        assert set(history['Driver ID'])=={'B'}
        assert 'Profile' in history.columns


def test_click_driver_name_navigates_after_sorting_and_paging():
    data=[{'Tms_ID':f'T{i:04}','Samsara_DriverID':f'D{i:04}','Samsara_DriverName':f'Driver {i:04}',
           'totalPTI':None,'CODRIVER_totalPTI':None} for i in range(60)]
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        next(item for item in dashboard.toggle if item.label=='Descending').set_value(True).run()
        next(item for item in dashboard.selectbox if item.label.startswith('Page ·')).set_value(2).run()
        grid=dashboard.dataframe[0]
        expected=grid.value.iloc[3]['Driver ID']
        states=dashboard._tree.get_widget_states()
        state=states.widgets.add();state.id=grid.proto.id
        state.string_value=json.dumps({'selection':{'cells':[[3,'Driver']],'rows':[],'columns':[]}})
        dashboard._run(states)
        assert not dashboard.exception
        assert 'Individual driver' in [item.value for item in dashboard.title]
        assert next(item for item in dashboard.selectbox if item.label=='Driver').value==expected


@pytest.mark.parametrize('partner_in_period',[False,True])
def test_trained_history_but_no_period_filter_respects_partner_and_training_dates(partner_in_period):
    data=rows()
    data[0]['appended_startTIme']=['2026-10-01T12:00:00Z']
    data[0]['appended_endTime']=['2026-10-01T12:05:00Z']
    partner_date='2026-11-23' if partner_in_period else '2026-10-02'
    data[0]['CODRIVER_appended_startTIme']=[partner_date+'T12:00:00Z']
    data[0]['CODRIVER_appended_endTime']=[partner_date+'T12:05:00Z']
    data[1].update(PTITraining='DONE',PTITrainingDate='2026-11-01') # Has a current-period record.
    data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-01') # No file evidence.
    data.append({'Tms_ID':'TF','Samsara_DriverID':'F','Samsara_DriverName':'Future training','PTITraining':'DONE',
                 'PTITrainingDate':'2026-11-24','totalPTI':1,'count_vehicleID':1,'count_trailerID':0,
                 'appended_startTIme':['2026-10-03T12:00:00Z'],'appended_endTime':['2026-10-03T12:05:00Z']})
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        next(item for item in dashboard.selectbox if item.label=='Training / DVIR follow-up').set_value('Training done · DVIR in file, none in period').run()
        assert not dashboard.exception
        if partner_in_period:
            assert not dashboard.dataframe
        else:
            frame=dashboard.dataframe[0].value
            assert frame['Driver ID'].tolist()==['A']
            assert str(frame['Latest own/co-driver DVIR date (file)'].iloc[0])=='2026-10-02'
            next(item for item in dashboard.radio if item.label=='Reporting period').set_value(15).run()
            assert dashboard.dataframe[0].value['Driver ID'].tolist()==['A']


def test_real_upload_survives_click_to_profile_and_next_rerun():
    dashboard=app().run()
    dashboard.file_uploader[0].set_value(('report.json',json.dumps(rows()).encode(),'application/json')).run()
    dashboard.switch_page('pages/11_TruckMate_Roster.py').run()
    assert not dashboard.exception
    grid=dashboard.dataframe[0]
    row=grid.value['Driver ID'].tolist().index('C')
    states=dashboard._tree.get_widget_states()
    state=states.widgets.add();state.id=grid.proto.id
    state.string_value=json.dumps({'selection':{'cells':[[row,'Driver']],'rows':[],'columns':[]}})
    dashboard._run(states)
    assert not dashboard.exception
    assert 'Individual driver' in [item.value for item in dashboard.title]
    assert next(item for item in dashboard.selectbox if item.label=='Driver').value=='C'
    assert 'Cara' in [item.value for item in dashboard.subheader]
    assert set(dashboard.dataframe[0].value['Driver ID'])=={'C'}
    # AppTest retains its original requested page; the browser follows the redirected profile URL.
    dashboard.switch_page('pages/3_Driver_Profiles.py').run()
    assert not dashboard.exception
    assert 'Cara' in [item.value for item in dashboard.subheader]
    assert set(dashboard.dataframe[0].value['Driver ID'])=={'C'}


def test_real_upload_removal_clears_the_session_copy():
    dashboard=app().run()
    dashboard.file_uploader[0].set_value(('report.json',json.dumps(rows()).encode(),'application/json')).run()
    assert dashboard.session_state['local-upload-contents']
    dashboard.file_uploader[0].set_value(None).run()
    assert not dashboard.exception
    assert not dashboard.dataframe and not dashboard.metric
    assert 'Upload your DVIR report' in [item.value for item in dashboard.title]
    assert 'local-upload-contents' not in dashboard.session_state
    assert 'local-model' not in dashboard.session_state


def test_real_upload_report_period_and_ending_date_survive_profile_click():
    from datetime import date
    dashboard=app().run()
    dashboard.file_uploader[0].set_value(('report.json',json.dumps(rows()).encode(),'application/json')).run()
    dashboard.switch_page('pages/11_TruckMate_Roster.py').run()
    next(item for item in dashboard.radio if item.label=='Reporting period').set_value(15).run()
    next(item for item in dashboard.date_input if item.label=='Report ending').set_value(date(2026,11,22)).run()
    grid=dashboard.dataframe[0]
    row=grid.value['Driver ID'].tolist().index('A')
    states=dashboard._tree.get_widget_states()
    state=states.widgets.add();state.id=grid.proto.id
    state.string_value=json.dumps({'selection':{'cells':[[row,'Profile']],'rows':[],'columns':[]}})
    dashboard._run(states)
    assert not dashboard.exception
    assert 'Individual driver' in [item.value for item in dashboard.title]
    assert 'Alice' in [item.value for item in dashboard.subheader]
    assert next(item for item in dashboard.radio if item.label=='Reporting period').value==15
    assert next(item for item in dashboard.date_input if item.label=='Report ending').value==date(2026,11,22)


def test_not_done_training_filter_includes_empty_unknown_and_not_values():
    data=rows();data[1]['PTITraining']='Unknown';data[2]['PTITraining']=''
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        training=next(item for item in dashboard.selectbox if item.label=='PTI training')
        assert training.options==['All','Done','Not done']
        training.set_value('Not done').run()
        assert not dashboard.exception
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'C','D'}
        next(item for item in dashboard.selectbox if item.label=='PTI training').set_value('Done').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['A']


def test_simple_report_has_five_tables_excel_and_a_fixed_fifteen_day_window():
    data=rows();data[1]['PTITraining']='DONE';data[1]['appended_startTIme']=['2026-11-10T14:00:00Z'];data[1]['appended_endTime']=['2026-11-10T14:05:00Z']
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/12_Simple_Report.py').run()
        assert not dashboard.exception
        assert 'Simple 15-day report' in [item.value for item in dashboard.title]
        assert [tab.label for tab in dashboard.tabs]==['Solo with DVIR','Solo without DVIR','Co-driver with DVIR','Co-driver without DVIR','No PTI in entire file']
        assert not dashboard.get('plotly_chart')
        assert not any(item.label=='Reporting period' for item in dashboard.radio)
        assert any(item.label=='Download Excel report (5 sheets)' for item in dashboard.get('download_button'))
        assert len([item for item in dashboard.get('download_button') if item.label=='Download this table (CSV)'])==5
        solo=next(item.value for item in dashboard.dataframe if 'Driver ID' in item.value.columns and 'C' in set(item.value['Driver ID']))
        assert solo['DVIRs (15 days)'].tolist()==[1]
        team=next(item.value for item in dashboard.dataframe if 'Driver names' in item.value.columns)
        assert team['Driver names'].tolist()==['Alice\nBob']


def test_simple_report_real_upload_clear_returns_to_empty():
    dashboard=app().run()
    dashboard.file_uploader[0].set_value(('report.json',json.dumps(rows()).encode(),'application/json')).run()
    dashboard.switch_page('pages/12_Simple_Report.py').run()
    assert not dashboard.exception and dashboard.dataframe
    next(item for item in dashboard.button if item.key=='local-clear-upload').click().run()
    assert not dashboard.exception and not dashboard.dataframe
    assert not dashboard.get('download_button')


def test_simple_report_days_off_and_solo_history_filters_combine():
    data=rows()
    data[1].update(PTITraining='DONE',appended_startTIme=['2026-11-01T14:00:00Z'],
                   appended_endTime=['2026-11-01T14:05:00Z'])
    data[2]['PTITraining']='DONE'
    data.append({'Tms_ID':'TE','Samsara_DriverID':'E','Samsara_DriverName':'Evan','PTITraining':'DONE'})
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/12_Simple_Report.py').run()
        assert not dashboard.exception

        # The default never-recorded follow-up excludes positive days off.
        assert dashboard.tabs[4].dataframe[0].value['Driver ID'].tolist()==['E']
        dashboard.selectbox(key='view-stakeholder-days-off-No PTI in entire file').set_value('Has days off').run()
        assert dashboard.tabs[4].dataframe[0].value['Driver ID'].tolist()==['D']
        dashboard.selectbox(key='view-stakeholder-solo-history').set_value('Has records in file').run()
        assert dashboard.tabs[1].dataframe[0].value['Driver ID'].tolist()==['C']
        dashboard.selectbox(key='view-stakeholder-days-off-Solo without DVIR').set_value('Has days off').run()
        assert not dashboard.tabs[1].dataframe
        dashboard.selectbox(key='view-stakeholder-solo-history').set_value('No record in entire file').run()
        assert dashboard.tabs[1].dataframe[0].value['Driver ID'].tolist()==['D']
        assert not dashboard.exception


def test_tracking_snapshot_cards_and_dropdown_show_the_underlying_drivers():
    with upload_mock():
        dashboard=app().run()
        cards={item.label:item.value for item in dashboard.metric}
        assert cards['TruckMate roster drivers']=='3'
        assert cards['Drivers with DVIR']=='2' and cards['Drivers without DVIR']=='1'
        assert cards['DVIR submissions']=='4'
        assert cards['Has days off']=='1' and cards['No days off reported']=='2'
        assert cards['PTI training Done']=='1' and cards['PTI training Not done']=='2'
        assert cards['Training Not done · own DVIR in 15 days']=='1'
        assert cards['Training Not done · dated own DVIR in file']=='1'
        assert cards['Drivers who submitted on a marked day off']=='0'
        dashboard.selectbox(key='view-tracking-list').set_value('Training Not done · own DVIR in 15 days').run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['C']
        assert dashboard.dataframe[0].value['PTI training'].tolist()==['Not done']
        dashboard.selectbox(key='view-tracking-list').set_value('No DVIR · has days off').run()
        assert not dashboard.exception
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        assert dashboard.dataframe[0].value['PTI training'].tolist()==['Not done']
        dashboard.selectbox(key='view-tracking-list').set_value('With DVIR in these 15 days').run()
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'A','C'}


def test_tracking_source_review_list_includes_explanations_and_next_steps():
    data=rows();data[1]['totalPTI']=4
    with upload_mock(data):
        dashboard=app().run()
        dashboard.selectbox(key='view-tracking-list').set_value('Source data checks only').run()
        assert not dashboard.exception
        frame=dashboard.dataframe[0].value
        assert frame['Driver ID'].tolist()==['C']
        assert {'Data checks','Check details','Suggested next step','Review category'}.issubset(frame.columns)
        assert 'Reported count differs from timestamps' in frame.iloc[0]['Data checks']
        assert 'training record' in frame.iloc[0]['Suggested next step']
        assert any(link.proto.label=='Open all source checks and unmatched authors' for link in dashboard.get('page_link'))


def test_excel_download_in_sidebar_is_available_from_any_page_and_clears():
    dashboard=app().run()
    assert not dashboard.sidebar.get('download_button')
    dashboard.file_uploader[0].set_value(('report.json',json.dumps(rows()).encode(),'application/json')).run()
    for page in ['pages/1_Fleet_Overview.py','pages/4_Co_Driver_Analysis.py','pages/3_Driver_Profiles.py']:
        dashboard.switch_page(page).run()
        assert not dashboard.exception
        assert any(item.label=='Download Excel report (5 sheets)' for item in dashboard.sidebar.get('download_button'))
    cache=dashboard.session_state['view-sidebar-report-cache']
    from openpyxl import load_workbook
    from io import BytesIO
    workbook=load_workbook(BytesIO(cache[1]),read_only=True)
    assert workbook.sheetnames==['Solo with DVIR','Solo without DVIR','Co-driver with DVIR','Co-driver without DVIR','No PTI in entire file']
    next(item for item in dashboard.button if item.key=='local-clear-upload').click().run()
    assert not dashboard.sidebar.get('download_button')
    assert 'view-sidebar-report-cache' not in dashboard.session_state


def test_training_not_done_section_includes_blank_unknown_and_co_roster_only():
    data=rows();data[0]['PTITraining']=None;data[1]['PTITraining']='Unknown';data[2]['PTITraining']='Not'
    with upload_mock(data):
        dashboard=app().run().switch_page('pages/13_PTI_Training.py').run()
        assert not dashboard.exception
        assert 'PTI training not done' in [item.value for item in dashboard.title]
        frame=dashboard.dataframe[0].value
        assert set(frame['Driver ID'])=={'A','C','D'}
        assert set(frame['PTI training'])=={'Not done'}
        assert 'TruckMate / TMW ID' in frame.columns
        assert any(item.label=='Download CSV' for item in dashboard.get('download_button'))
        assert any(item.label=='Download Excel report (5 sheets)' for item in dashboard.sidebar.get('download_button'))
        next(item for item in dashboard.selectbox if item.label=='Driver arrangement').set_value('Co-driver').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['A']
        next(item for item in dashboard.text_input if item.key=='view-training-not-done-search').set_value('TA').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['A']


def test_training_not_done_section_excludes_done_but_keeps_zero_dvir_drivers():
    with upload_mock():
        dashboard=app().run().switch_page('pages/13_PTI_Training.py').run()
        assert not dashboard.exception
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'C','D'}
        assert dashboard.dataframe[0].value.set_index('Driver ID').loc['D','DVIRs in period']==0


def test_main_navigation_keeps_all_other_pages_in_one_backend_group():
    with upload_mock():
        dashboard=app().run()
        assert not dashboard.exception
        backend=next(item for item in dashboard.sidebar.expander if item.label=='Backend')
        assert [item.proto.label for item in backend.get('page_link')]==[
            'Solo with DVIR','Solo without DVIR','Main TruckMate roster','Co-driver teams','Individual driver','Data checks & unmatched']
        all_links=[item.proto.label for item in dashboard.sidebar.get('page_link')]
        assert all_links[:3]==['Simple 15-day report','PTI training not done','Overview']
        assert backend.proto.expanded is False
        for page in ['pages/2_Driver_Consistency.py','pages/10_Without_DVIR.py','pages/11_TruckMate_Roster.py',
                     'pages/4_Co_Driver_Analysis.py','pages/3_Driver_Profiles.py','pages/9_Unmatched_Review.py']:
            dashboard.switch_page(page).run()
            assert not dashboard.exception


def test_roster_and_profile_use_days_off_labels_without_holiday_text():
    with upload_mock():
        dashboard=app().run().switch_page('pages/11_TruckMate_Roster.py').run()
        assert not dashboard.exception
        frame=dashboard.dataframe[0].value
        assert 'Days off status (period)' in frame.columns
        assert 'Days off in period' in frame.columns
        assert not any('holiday' in str(column).lower() for column in frame.columns)
        next(item for item in dashboard.selectbox if item.label=='Days off status (period)').set_value('Partly on holiday').run()
        assert dashboard.dataframe[0].value['Driver ID'].tolist()==['D']
        assert dashboard.dataframe[0].value['Days off status (period)'].tolist()==['Some days off']
        dashboard.switch_page('pages/3_Driver_Profiles.py').run()
        next(item for item in dashboard.selectbox if item.label=='Driver').set_value('D').run()
        assert not dashboard.exception
        calendar=next(item.value for item in dashboard.dataframe if 'Status' in item.value.columns)
        assert 'Day off' in set(calendar.Status)
        assert not any('holiday' in item.value.lower() for item in dashboard.caption)


def test_not_done_drivers_stay_in_training_section_not_solo_or_never_reports():
    with upload_mock():
        dashboard=app().run().switch_page('pages/13_PTI_Training.py').run()
        assert not dashboard.exception
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'C','D'}
        for page in ('pages/2_Driver_Consistency.py','pages/10_Without_DVIR.py'):
            dashboard.switch_page(page).run()
            assert not dashboard.exception
            assert not dashboard.dataframe
        dashboard.switch_page('pages/12_Simple_Report.py').run()
        assert not dashboard.exception
        assert all('Driver ID' not in item.value.columns for item in dashboard.dataframe)
        dashboard.switch_page('pages/13_PTI_Training.py').run()
        assert set(dashboard.dataframe[0].value['Driver ID'])=={'C','D'}
