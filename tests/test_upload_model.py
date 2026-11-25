import json
from copy import deepcopy
from datetime import date,timedelta
import pytest
from src.upload_model import parse_upload,people_summary,crew_summary,UploadError


def rows():
    return [
      {'Tms_ID':'TA','Tms_driverName':'Alice','Samsara_DriverID':'A','Samsara_DriverName':'Alice','COGOELD':'CA',
       'driverID':'B','driverName':'Alice','samsara_driverId':'B','samsara_driverName':'Bob','SamsaraStatus':'active',
       'count_vehicleID':1,'count_trailerID':1,'totalPTI':2,'unique_count_driverID':1,
       'appended_startTIme':['2026-11-21T12:00:00Z','2026-11-22T12:00:00Z'],
       'appended_endTime':['2026-11-21T12:10:00Z','2026-11-22T12:10:00Z'],
       'appended_vehicleName':['Truck 7'],'appended_trailerID':['T1'],
       'CODRIVER_driverID':'B','CODRIVER_driverName':'Bob','CODRIVER_totalPTI':1,
       'CODRIVER_count_vehicleID':1,'CODRIVER_count_trailerID':0,
       'CODRIVER_appended_startTIme':['2026-11-23T13:00:00Z'],'CODRIVER_appended_endTime':['2026-11-23T13:05:00Z'],
       'CODRIVER_appended_vehicleName':['Truck 7'],'CODRIVER_appended_trailerID':[],
       'matched_on':'cogoID_1','vehicleName':'Truck 7','cogoID_0':'CA','driverName_0':'Alice','cogoID_1':'CB','driverName_1':'Bob',
       'PTITraining':'Done','PTITrainingDate':'2026-11-01'},
      {'Tms_ID':'TC','Samsara_DriverID':'C','Samsara_DriverName':'Cara','driverID':'C','driverName':'Cara',
       'samsara_driverId':'C','SamsaraStatus':'deactive','totalPTI':1,'count_vehicleID':1,'count_trailerID':0,
       'appended_startTIme':['2026-11-23T14:00:00Z'],'appended_endTime':['2026-11-23T14:04:00Z'],
       'appended_vehicleName':['Truck 8'],'appended_trailerID':[],'CODRIVER_totalPTI':None},
      {'Tms_ID':'TD','Samsara_DriverID':'D','Samsara_DriverName':'Dana','totalPTI':None,
       'count_status_date':1,'appended_status_date':'2026-11-23','CODRIVER_totalPTI':None}]


def report(data=None):return parse_upload(json.dumps(rows() if data is None else data).encode())
def window(end=date(2026,11,23),days=7):return [end-timedelta(days=i) for i in reversed(range(days))]


def test_explicit_codriver_does_not_overwrite_primary_identity():
    r=report();s=people_summary(r,window(),r.latest).set_index('driver_id')
    assert len(s[s.in_roster])==3
    assert s.loc['A','dated_PTIs']==2 and s.loc['B','dated_PTIs']==1
    assert s.loc['A','reported_totalPTI']==2 and s.loc['B','reported_totalPTI']==1
    assert not s.loc['B','in_roster'] and s.loc['B','has_crew']
    assert s.loc['A','samsara_status']=='Unknown'
    assert s.loc['B','samsara_status']=='Active'
    assert s.loc['C','samsara_status']=='Deactivated'
    assert set(s.loc[~s.has_own_DVIR].index)=={'D'}
    assert len(r.events)==4 and r.latest==date(2026,11,23)
    assert s.loc['A','pti_training_status']=='Done'
    assert s.loc['B','pti_training_status']=='Not done'


def test_combined_crew_keeps_counts_dates_duration_and_each_author():
    r=report();team=crew_summary(r,window(),r.latest).iloc[0]
    assert team.members=={'A','B'}
    assert team.dated_PTIs==3 and team.recorded_dates==3
    assert team.reported_vehicle_count==2 and team.reported_trailer_count==1 and team.reported_totalPTI==3
    assert team.known_duration_minutes==25 and team.duration_records==3
    assert 'Alice: 2' in team.each_person_own_PTIs and 'Bob: 1' in team.each_person_own_PTIs


def test_codriver_only_does_not_turn_into_a_primary_submission():
    data=rows();data[0].update(totalPTI=None,appended_startTIme=None,appended_endTime=None,count_vehicleID=None,count_trailerID=None)
    r=report(data);s=people_summary(r,window(),r.latest).set_index('driver_id')
    assert not s.loc['A','has_own_DVIR'] and s.loc['A','dated_PTIs']==0
    assert s.loc['A','partner_PTIs_in_period']==1
    assert crew_summary(r,window(),r.latest).iloc[0].dated_PTIs==1


def test_reciprocal_or_repeated_blocks_do_not_double_inspections():
    data=rows();data.append(deepcopy(data[0]));r=report(data)
    assert len(r.events)==4
    assert crew_summary(r,window(),r.latest).iloc[0].reported_totalPTI==3


def test_team_regularity_is_union_of_members_dates():
    data=rows();data[0]['CODRIVER_totalPTI']=2;data[0]['CODRIVER_count_vehicleID']=2
    data[0]['CODRIVER_appended_startTIme']=['2026-11-20T13:00:00Z','2026-11-23T13:00:00Z']
    data[0]['CODRIVER_appended_endTime']=['2026-11-20T13:05:00Z','2026-11-23T13:05:00Z']
    r=report(data);s=people_summary(r,window(),r.latest).set_index('driver_id')
    assert s.loc['A','consistency']=='Intermittent' and s.loc['B','consistency']=='Intermittent'
    assert crew_summary(r,window(),r.latest).iloc[0].consistency=='Regular'


def test_actual_record_on_holiday_is_retained_and_no_record_holiday_excluded():
    r=report();s=people_summary(r,window(),r.latest).set_index('driver_id')
    assert s.loc['D','availability']=='Partly on holiday'
    assert s.loc['D','nonholiday_dates_without_record']==6
    data=rows();data[1].update(appended_status_date='2026-11-23',count_status_date=1)
    r=report(data);s=people_summary(r,window(),r.latest).set_index('driver_id')
    assert s.loc['C','on_selected_date'] and s.loc['C','availability']=='Partly on holiday'


def test_missing_primary_samsara_id_is_not_filled_with_partner_id():
    data=rows();data[0]['Samsara_DriverID']=None;r=report(data)
    assert 'tms:TA' in set(r.people.driver_id)
    assert len(r.events[r.events.driver_id.eq('tms:TA')])==2
    assert len(r.events[r.events.driver_id.eq('B')])==1


def test_file_replacement_has_no_history_from_previous_upload():
    before=report();after=report([rows()[2]])
    assert len(before.events)==4 and after.events.empty
    assert set(after.people.driver_id)=={'D'}


def test_bad_json_and_scalar_date_arrays_are_rejected():
    with pytest.raises(UploadError):parse_upload(b'not-json')
    data=rows();data[0]['CODRIVER_appended_startTIme']='2026-11-23'
    with pytest.raises(UploadError):report(data)


def test_legacy_grouped_driver_data_without_roster_stays_visible_as_unmatched():
    r=report([{'driverID':'X','driverName':'Extra','totalPTI':1,'startTimes':['2026-11-23T12:00:00Z'],
               'endTimes':['2026-11-23T12:01:00Z'],'vehicleNames':['Truck X']}])
    assert r.people.iloc[0].driver_id=='X' and not r.people.iloc[0].in_roster
    assert len(r.events)==1



def test_positive_summary_without_dates_is_reviewed_instead_of_confirmed_missing():
    r=report([{'Tms_ID':'TS','Samsara_DriverID':'S','Samsara_DriverName':'Summary only',
               'totalPTI':3,'count_vehicleID':3,'count_trailerID':0,'CODRIVER_totalPTI':None}])
    s=people_summary(r,window(r.latest),r.latest).iloc[0]
    assert s.has_own_DVIR and s.consistency=='Needs date detail' and s.needs_review
    assert r.events.empty



def test_subset_block_does_not_double_full_file_reported_counts():
    data=rows();extra=deepcopy(data[0]);extra['Tms_ID']='TX';extra['Samsara_DriverID']='X';extra['Samsara_DriverName']='Extra roster'
    extra['totalPTI']=None;extra['appended_startTIme']=None;extra['appended_endTime']=None
    extra['CODRIVER_driverID']='A';extra['CODRIVER_driverName']='Alice';extra['CODRIVER_totalPTI']=1
    extra['CODRIVER_appended_startTIme']=['2026-11-21T12:00:00Z'];extra['CODRIVER_appended_endTime']=['2026-11-21T12:10:00Z']
    data.append(extra);r=report(data);s=people_summary(r,window(),r.latest).set_index('driver_id')
    assert s.loc['A','dated_PTIs']==2 and s.loc['A','reported_totalPTI']==2
    assert not r.blocks[r.blocks.driver_id.eq('A')].counted_in_totals.all()


def test_partial_overlap_keeps_dated_records_and_flags_source_totals():
    data=rows();extra=deepcopy(data[0]);extra['appended_startTIme']=['2026-11-22T12:00:00Z','2026-11-23T12:00:00Z']
    extra['appended_endTime']=['2026-11-22T12:10:00Z','2026-11-23T12:10:00Z'];data.append(extra)
    r=report(data);s=people_summary(r,window(),r.latest).set_index('driver_id')
    assert s.loc['A','dated_PTIs']==3
    assert __import__('pandas').isna(s.loc['A','reported_totalPTI'])
    assert s.loc['A','needs_review']



def test_source_categories_are_exclusive_and_cover_the_primary_roster():
    r=report();frame=people_summary(r,window(),r.latest)
    roster=frame[frame.in_roster]
    groups={label:set(roster.loc[roster.category.eq(label),'driver_id']) for label in ('Co-driver','Solo with DVIR','Solo without DVIR')}
    assert groups=={'Co-driver':{'A'},'Solo with DVIR':{'C'},'Solo without DVIR':{'D'}}
    assert set.union(*groups.values())==set(roster.driver_id)
    assert all(not (groups[a]&groups[b]) for a in groups for b in groups if a!=b)
    assert frame.set_index('driver_id').loc['B','category']=='Outside primary roster'


def test_category_does_not_change_with_date_window_or_submission_frequency():
    r=report()
    current=people_summary(r,window(),r.latest).set_index('driver_id')
    earlier=date(2026,11,20)
    previous=people_summary(r,window(earlier,15),earlier).set_index('driver_id')
    assert current.category.to_dict()==previous.category.to_dict()
    assert previous.loc['C','dated_PTIs']==0
    assert previous.loc['C','consistency']=='No record in period'


def test_positive_equipment_counts_are_evidence_but_lookup_fields_alone_are_not():
    data=rows()+[
       {'Tms_ID':'TE','Samsara_DriverID':'E','Samsara_DriverName':'Equipment evidence','count_vehicleID':2,'CODRIVER_totalPTI':None},
       {'Tms_ID':'TF','Samsara_DriverID':'F','Samsara_DriverName':'Lookup only','driverID':'F','samsara_driverId':'F',
        'vehicleName':'Assigned truck','CODRIVER_totalPTI':None}]
    r=report(data);frame=people_summary(r,window(),r.latest).set_index('driver_id')
    assert frame.loc['E','category']=='Solo with DVIR'
    assert frame.loc['E','consistency']=='Needs date detail'
    assert frame.loc['F','category']=='Solo without DVIR'


def test_co_driver_columns_take_priority_even_without_any_inspection_block():
    row={'Tms_ID':'TZ','Samsara_DriverID':'Z','Samsara_DriverName':'Crew only','COGOELD':'CZ',
         'vehicleName':'Truck Z','cogoID_0':'CZ','driverName_0':'Crew only','cogoID_1':'CY','driverName_1':'Partner',
         'matched_on':'cogoID_1','CODRIVER_totalPTI':None}
    r=report([row]);frame=people_summary(r,window(r.latest),r.latest).iloc[0]
    assert not frame.has_own_DVIR
    assert frame.category=='Co-driver'


def test_training_follows_primary_identity_and_explicit_partner_fields_only():
    data=rows();data[0]['CODRIVER_PTITraining']='Not done'
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['A','pti_training_status']=='Done'
    assert s.loc['A','pti_training_date']=='2026-11-01'
    assert s.loc['B','pti_training_status']=='Not done'
    assert s.loc['C','pti_training_status']=='Not done'


def test_training_followup_distinguishes_period_gap_from_absent_file_evidence():
    data=rows();data[0]['appended_startTIme']=['2026-10-01T12:00:00Z'];data[0]['appended_endTime']=['2026-10-01T12:05:00Z']
    data[2]['PTITraining']='DONE'
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['A','training_done_no_dvir_in_period']
    assert not s.loc['A','training_done_no_dvir_in_file']
    assert s.loc['D','training_done_no_dvir_in_period'] and s.loc['D','training_done_no_dvir_in_file']
    assert not s.loc['B','training_done_no_dvir_in_period']
    assert s.loc['A','category']=='Co-driver'


def test_conflicting_training_status_is_not_marked_done():
    from copy import deepcopy
    data=rows();other=deepcopy(data[0]);other['PTITraining']='Not done';data.append(other)
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['A','pti_training_status']=='Not done'
    assert not s.loc['A','training_done_no_dvir_in_file']


def test_partner_only_submission_covers_driver_without_changing_authorship():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None)
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert not s.loc['A','has_own_DVIR']
    assert s.loc['A','has_covered_DVIR'] and s.loc['A','has_partner_DVIR']
    assert s.loc['A','dvir_coverage']=='Co-driver DVIR'
    assert s.loc['A','covered_dates_in_period']==1
    assert s.loc['A','covered_on_selected_date']
    assert s.loc['A','dated_PTIs']==0 and s.loc['B','dated_PTIs']==1
    assert not s.loc['D','has_covered_DVIR']


def test_neither_member_submitting_requires_followup_and_no_cross_team_credit():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None,
                             CODRIVER_totalPTI=None,CODRIVER_count_vehicleID=None,CODRIVER_count_trailerID=None,
                             CODRIVER_appended_startTIme=None,CODRIVER_appended_endTime=None)
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert not s.loc['A','has_covered_DVIR'] and not s.loc['B','has_covered_DVIR']
    assert s.loc['C','has_covered_DVIR'] # An unrelated solo driver's submission cannot cover A or B.
    assert s.loc['A','coverage_consistency']=='No record in period'


def test_coverage_dates_union_both_members_without_counting_same_day_twice():
    data=rows();data[0]['CODRIVER_appended_startTIme']=['2026-11-22T13:00:00Z'];data[0]['CODRIVER_appended_endTime']=['2026-11-22T13:05:00Z']
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['A','covered_dates_in_period']==2
    assert s.loc['B','covered_dates_in_period']==2
    assert s.loc['A','dated_PTIs']==2 and s.loc['B','dated_PTIs']==1
    assert not s.loc['A','covered_on_selected_date']


def test_holiday_status_uses_entire_window_not_just_ending_date():
    data=rows();data[2]['appended_status_date']=['2026-11-18','2026-11-19'];data[2]['count_status_date']=2
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['D','availability']=='Partly on holiday'
    assert not s.loc['D','holiday_on_report_date']
    assert s.loc['D','holiday_dates_in_period']==2
    assert s.loc['D','coverage_dates_without_recorded_holiday']==5
    assert s.loc['A','availability']=='Unknown'


def test_full_period_holiday_has_no_uncovered_dates_and_explicit_zero_is_distinct():
    data=rows();data[2]['appended_status_date']=[day.isoformat() for day in window()];data[2]['count_status_date']=7
    data[1]['count_status_date']=0;data[1]['appended_status_date']=[]
    r=report(data);s=people_summary(r,window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['D','availability']=='On holiday all period'
    assert s.loc['D','coverage_dates_without_recorded_holiday']==0
    assert s.loc['C','availability']=='No holiday dates reported'
    longer=people_summary(r,window(days=15),date(2026,11,23)).set_index('driver_id')
    assert longer.loc['D','availability']=='Partly on holiday'
    assert longer.loc['D','holiday_dates_in_period']==7


def test_partner_submission_and_own_holiday_are_excluded_from_period_gaps():
    data=rows();data[0]['appended_status_date']=['2026-11-20'];data[0]['count_status_date']=1
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['A','covered_dates_in_period']==3
    assert s.loc['A','coverage_dates_without_recorded_holiday']==3
    assert s.loc['B','availability']=='Unknown' # Do not copy Alice's holiday to Bob.


@pytest.mark.parametrize('days',[7,15])
def test_training_after_period_excludes_no_dvir_followup(days):
    data=rows();data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-24')
    s=people_summary(report(data),window(days=days),date(2026,11,23)).set_index('driver_id')
    assert s.loc['D','training_period_status']=='Trained after period'
    assert not s.loc['D','training_followup_eligible']
    assert not s.loc['D','training_done_no_dvir_in_period']
    assert not s.loc['D','training_done_no_dvir_in_file']
    assert s.loc['D','coverage_dates_without_recorded_holiday']==0
    assert s.loc['D','coverage_consistency']=='Trained after period'
    assert s.loc['D','pti_training_status']=='Done' # Preserve actual completion status.


def test_training_during_period_only_counts_dates_after_training_day():
    data=rows();data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-20',appended_status_date=['2026-11-22'])
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['D','training_period_status']=='Trained during period'
    assert s.loc['D','training_followup_eligible']
    assert s.loc['D','post_training_dates']=={date(2026,11,21),date(2026,11,22),date(2026,11,23)}
    assert s.loc['D','coverage_dates_without_recorded_holiday']==2


def test_explicit_not_trained_is_separate_from_unknown_and_preserves_actual_records():
    data=rows();data[2]['PTITraining']='Not done';data[1]['PTITraining']='Not done'
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert not s.loc['D','training_followup_eligible']
    assert s.loc['D','coverage_consistency']=='Not trained'
    assert s.loc['C','dated_PTIs']==1 and s.loc['C','has_covered_DVIR']
    assert s.loc['B','training_followup_eligible']
    assert s.loc['B','training_period_status']=='Training not recorded'


def test_training_on_report_day_has_no_complete_post_training_dates():
    data=rows();data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-23')
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['D','training_period_status']=='Training on report-ending date'
    assert not s.loc['D','training_followup_eligible']


@pytest.mark.parametrize('value',[None,'','   ','Unknown','unknown','NOT','Not done','Completed','yes',True,False,0,[],{}])
def test_only_done_is_training_done_other_values_are_not_done(value):
    from src.upload_model import training_status
    assert training_status(value)=='Not done'


@pytest.mark.parametrize('value',['DONE','done','Done','  DONE  '])
def test_done_training_is_case_and_whitespace_insensitive(value):
    from src.upload_model import training_status
    assert training_status(value)=='Done'


def test_missing_training_defaults_not_done_without_borrowing_partner_completion():
    data=rows();data[0].pop('PTITraining');data[0]['CODRIVER_PTITraining']='DONE'
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['A','pti_training_status']=='Not done'
    assert s.loc['B','pti_training_status']=='Done'
    assert s.loc['A','dated_PTIs']==2 and s.loc['B','dated_PTIs']==1
    assert s.loc['A','has_covered_DVIR']


def test_blank_training_labels_not_done_without_inventing_verified_incomplete():
    data=rows();data[2]['PTITraining']='Unknown'
    s=people_summary(report(data),window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['D','pti_training_status']=='Not done'
    assert not s.loc['D','training_explicitly_incomplete']
    assert s.loc['D','training_followup_eligible']
    assert s.loc['D','training_period_status']=='Training not recorded'
    assert s.loc['D','coverage_consistency']=='No record in period'


@pytest.mark.parametrize('values,expected',[(['safe'],'Safe'),(['safe','resolved'],'Resolved'),
    (['safe','resolved','unsafe'],'Unsafe'),(['safe','requiresRepair'],'requiresRepair'),([], 'Not supplied')])
def test_grouped_safety_precedence_does_not_imply_per_date_status(values,expected):
    data=rows();data[0]['safetyStatuses']=values
    r=report(data);s=people_summary(r,window(),date(2026,11,23)).set_index('driver_id')
    assert s.loc['A','safety_status_file']==expected
    assert s.loc['B','safety_status_file']=='Not supplied'
    assert s.loc['A','dated_PTIs']==2 and s.loc['B','dated_PTIs']==1
    assert 'safety_status_file' not in r.events.columns
