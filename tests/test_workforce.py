from copy import deepcopy
from datetime import date
import pytest
from src.data_adapter import adapt
from src.normalization import normalize
from src.filters import reporting_dates
from src.roster import roster_summary
from src.workforce import account_statuses,team_summary,review_drivers,source_crews


def workforce_rows():
    crew={'cogoID_0':'CA','driverName_0':'Alice','cogoID_1':'CB','driverName_1':'Bob','vehicleName':'Truck 7'}
    a={**crew,'Tms_ID':'TA','Tms_driverName':'Alice','Samsara_DriverID':'A','Samsara_DriverName':'Alice',
       'COGOELD':'CA','driverID':'A','driverName':'Alice','samsara_driverId':'A','SamsaraStatus':'active',
       'count_vehicleID':2,'count_trailerID':1,'totalPTI':2,'unique_count_driverID':1,
       'appended_startTIme':['2026-11-20T12:00:00Z','2026-11-21T12:00:00Z'],
       'appended_endTime':['2026-11-20T12:10:00Z','2026-11-21T12:10:00Z'],
       'appended_vehicleName':['Truck 7','Truck 7'],'appended_trailerID':['T1']}
    b={**crew,'Tms_ID':'TB','Tms_driverName':'Bob','Samsara_DriverID':'B','Samsara_DriverName':'Bob',
       'COGOELD':'CB','driverID':'B','driverName':'Bob','samsara_driverId':'B','SamsaraStatus':'deactive',
       'count_vehicleID':1,'count_trailerID':0,'totalPTI':1,'unique_count_driverID':1,
       'appended_startTIme':['2026-11-21T13:00:00Z'],'appended_endTime':['2026-11-21T13:05:00Z'],
       'appended_vehicleName':['Truck 7'],'appended_trailerID':[]}
    duplicate={**a,'Tms_ID':'TB','Samsara_DriverID':'B','Samsara_DriverName':'Bob','COGOELD':'CB'}
    solo={'Tms_ID':'TC','Samsara_DriverID':'C','Samsara_DriverName':'Cara','samsara_driverId':'C',
          'SamsaraStatus':'active','COGOELD':'CC','totalPTI':0,'count_vehicleID':0,'count_trailerID':0}
    def unmatched(key,status):
        return {'driverID':key,'driverName':key,'samsara_driverId':key,'samsara_driverName':key,
                'SamsaraStatus':status,'count_vehicleID':1,'count_trailerID':0,'totalPTI':1,'unique_count_driverID':1,
                'appended_startTIme':['2026-11-22T13:00:00Z'],'appended_endTime':['2026-11-22T13:06:00Z'],
                'appended_vehicleName':['Review truck'],'appended_trailerID':[]}
    return [a,b,duplicate,solo,unmatched('U','active'),unmatched('V','deactive'),unmatched('W',None)]


def test_status_scopes_solo_teams_and_reported_counts_are_not_duplicated():
    data=normalize(adapt(workforce_rows()),'America/Chicago')
    dates=reporting_dates(7,date(2026,11,23))
    statuses=account_statuses(data)
    assert statuses['A']=='Active' and statuses['B']=='Deactivated'
    summary=roster_summary(data,dates,dates[-1]).set_index('driver_id')
    assert summary.loc['C','driver_mode']=='Solo'
    assert summary.loc['A','driver_mode']=='Co-driver'
    assert not summary.loc['U','in_roster']
    teams=team_summary(data,dates)
    assert len(teams)==1
    row=teams.iloc[0]
    assert row.samsara_status=='Mixed'
    assert row.combined_dated_PTIs==3
    assert row.source_vehicle_count_full_file==3
    assert row.source_trailer_count_full_file==1
    assert row.source_combined_equipment_count_full_file==4
    assert row.source_totalPTI_full_file==3
    assert row.combined_recorded_dates==2
    assert row.known_duration_minutes==25
    assert summary.loc['A','PTI_records']==2 and summary.loc['B','PTI_records']==1
    review=review_drivers(data,dates).set_index('driver_id')
    assert set(review.index)=={'U','V','W'}
    assert review.loc['U','samsara_status']=='Active'
    assert review.loc['V','samsara_status']=='Deactivated'
    assert review.loc['W','samsara_status']=='Unknown'


def test_multi_author_aggregate_is_not_divided_or_added_to_individual_totals():
    rows=workforce_rows()
    aggregate=deepcopy(rows[0]);aggregate['unique_count_driverID']=2
    rows.append(aggregate)
    data=normalize(adapt(rows),'America/Chicago')
    dates=reporting_dates(7,date(2026,11,23))
    teams=team_summary(data,dates)
    row=teams.iloc[0]
    assert row.multi_author_aggregate
    assert row.combined_dated_PTIs is None or __import__('pandas').isna(row.combined_dated_PTIs)
    assert row.source_totalPTI_full_file is None or __import__('pandas').isna(row.source_totalPTI_full_file)
    assert 'review' in row.source_count_note.lower()
    assert len(data.dvir_records[data.dvir_records.author_id.eq('A')])==2


def test_unmatched_only_json_keeps_authors_in_review_and_reads_appended_arrays():
    data=normalize(adapt(workforce_rows()[-3:]),'America/Chicago')
    dates=reporting_dates(7,date(2026,11,23))
    summary=roster_summary(data,dates,dates[-1])
    assert not summary.in_roster.any()
    assert len(review_drivers(data,dates))==3
    assert len(data.dvir_records)==3
    assert data.dvir_records.inspection_time.notna().all()


def test_status_is_not_inferred_from_holiday_or_submission_activity():
    row=workforce_rows()[-1]
    row['appended_status_date']='2026-11-23'
    data=normalize(adapt([row]),'America/Chicago')
    assert account_statuses(data).get('W','Unknown')=='Unknown'



def test_conflicting_statuses_are_unknown_and_flagged_for_review():
    from src.roster_audit import roster_audit
    rows=workforce_rows()
    conflicting=deepcopy(rows[0]);conflicting['SamsaraStatus']='deactive';rows.append(conflicting)
    data=normalize(adapt(rows),'America/Chicago')
    assert account_statuses(data)['A']=='Unknown'
    assert 'Conflicting Samsara account statuses' in set(roster_audit(data).check)


def test_missing_author_dates_are_not_marked_as_non_submission():
    rows=workforce_rows()
    row=deepcopy(rows[0]);row.pop('driverID');row['unique_count_driverID']=1
    data=normalize(adapt([row]),'America/Chicago')
    dates=reporting_dates(7,date(2026,11,23))
    summary=roster_summary(data,dates,dates[-1]).set_index('driver_id')
    assert summary.loc['A','consistency']=='Needs individual DVIR detail'
    assert data.dvir_records.empty


def test_unmatched_authors_stay_outside_main_roster_but_in_all_driver_export():
    from src.filters import apply_filters,Filters
    from src.rating_report import build_rating_report
    data=normalize(adapt(workforce_rows()),'America/Chicago')
    dates=reporting_dates(7,date(2026,11,23))
    assert set(apply_filters(data,dates,Filters()).drivers.driver_id)=={'A','B','C'}
    report=build_rating_report(data,dates,'America/Chicago').set_index('driver_id')
    assert set(report.index)=={'A','B','C','U','V','W'}
    assert report.loc['U','roster_match']=='Needs review'
    assert report.loc['C','roster_match']=='Matched roster'



def test_standalone_team_aggregate_counts_pairs_without_individual_credit():
    row=deepcopy(workforce_rows()[0]);row.pop('driverID');row['unique_count_driverID']=2
    data=normalize(adapt([row]),'America/Chicago')
    dates=reporting_dates(7,date(2026,11,23))
    teams=team_summary(data,dates)
    assert data.dvir_records.empty
    assert teams.iloc[0].combined_dated_PTIs==2
    assert teams.iloc[0].dated_count_basis.startswith('Unattributed team')
    assert teams.iloc[0].known_duration_minutes==20



def test_conflicting_reported_counts_are_not_summed_as_new_activity():
    rows=workforce_rows()
    inconsistent=deepcopy(rows[0]);inconsistent['totalPTI']=99;rows.append(inconsistent)
    data=normalize(adapt(rows),'America/Chicago')
    teams=team_summary(data,reporting_dates(7,date(2026,11,23)))
    assert teams.iloc[0].combined_dated_PTIs==3
    assert teams.iloc[0].source_totalPTI_full_file is None or __import__('pandas').isna(teams.iloc[0].source_totalPTI_full_file)
    assert teams.iloc[0].source_count_note.startswith('Conflicting counts')


def test_equivalent_utc_and_offset_timestamp_histories_do_not_double_counts():
    rows=workforce_rows()
    equivalent=deepcopy(rows[0])
    equivalent['appended_startTIme']=['2026-11-20T06:00:00-06:00','2026-11-21T06:00:00-06:00']
    equivalent['appended_endTime']=['2026-11-20T06:10:00-06:00','2026-11-21T06:10:00-06:00']
    rows.append(equivalent)
    data=normalize(adapt(rows),'America/Chicago')
    team=team_summary(data,reporting_dates(7,date(2026,11,23))).iloc[0]
    assert team.source_totalPTI_full_file==3
    assert team.combined_dated_PTIs==3
