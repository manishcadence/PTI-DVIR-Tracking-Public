import json
from datetime import date,timedelta

from src.tracking_overview import tracking_snapshot,training_review_top_five
from src.upload_model import parse_upload
from test_upload_model import rows


def snapshot(data=None,end=date(2026,11,23)):
    return tracking_snapshot(parse_upload(json.dumps(rows() if data is None else data).encode()),end)


def test_roster_coverage_and_inspection_totals_are_different_units():
    s=snapshot()
    assert len(s.dates)==15 and s.dates[0]==date(2026,11,9)
    assert set(s.roster.driver_id)=={'A','C','D'}
    assert s.roster.Submitted.sum()==2
    assert len(s.events)==4
    assert s.daily['DVIR submissions'].sum()==4
    assert s.daily.loc[s.daily.Date.eq(date(2026,11,23)),'Drivers covered'].item()==2


def test_partner_only_covers_roster_without_adding_partner_to_roster():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,
        appended_startTIme=None,appended_endTime=None)
    s=snapshot(data);r=s.roster.set_index('driver_id')
    assert r.loc['A','Submitted'] and r.loc['A','dated_PTIs']==0
    assert len(s.events)==2 and len(r)==3


def test_zero_and_missing_days_off_group_together_but_dates_use_window():
    data=rows();data[1].update(count_status_date=0,appended_status_date=[])
    r=snapshot(data).roster.set_index('driver_id')
    assert r.loc['A','Days off group']==r.loc['C','Days off group']=='No days off reported'
    assert r.loc['D','Days off group']=='Has days off'
    assert not r.loc['A','holiday_data_available'] and r.loc['C','holiday_data_available']
    assert snapshot(data,date(2026,11,22)).roster.set_index('driver_id').loc['D','Days off group']=='No days off reported'


def test_recent_training_requires_done_and_date_inside_inclusive_window():
    data=rows();data[0]['PTITrainingDate']='2026-11-09'
    data[1].update(PTITraining='DONE',PTITrainingDate='2026-11-23')
    data[2].update(PTITraining='Not',PTITrainingDate='2026-11-22')
    r=snapshot(data).roster.set_index('driver_id')
    assert set(r.index[r['Recently trained']])=={'A','C'}
    data[0]['PTITrainingDate']='2026-11-08';data[1]['PTITrainingDate']='2026-11-24'
    assert not snapshot(data).roster['Recently trained'].any()


def test_many_submissions_on_one_day_do_not_establish_regularity():
    data=rows();data[1].update(PTITraining='DONE',PTITrainingDate='2026-11-01',totalPTI=10,
        appended_startTIme=[f'2026-11-23T{hour:02d}:00:00Z' for hour in range(10,20)],
        appended_endTime=[f'2026-11-23T{hour:02d}:05:00Z' for hour in range(10,20)])
    r=snapshot(data).roster.set_index('driver_id')
    assert r.loc['C','dated_PTIs']==10
    assert r.loc['C','Submission pattern']=='Some dates recorded'
    days=[date(2026,11,23)-timedelta(days=i) for i in range(8)]
    data[1].update(totalPTI=8,appended_startTIme=[f'{d}T12:00:00Z' for d in days],
        appended_endTime=[f'{d}T12:05:00Z' for d in days])
    assert snapshot(data).roster.set_index('driver_id').loc['C','Submission pattern']=='Regular'


def test_unrelated_author_is_not_counted_in_roster_submissions():
    data=rows()+[{'driverID':'OUTSIDE','driverName':'Outside Example','totalPTI':1,
        'appended_startTIme':['2026-11-23T12:00:00Z'],'appended_endTime':['2026-11-23T12:05:00Z']}]
    assert len(snapshot(data).events)==4


def test_days_off_and_submission_in_same_period_are_not_always_same_day():
    data=rows();data[1].update(count_status_date=1,appended_status_date=['2026-11-22'])
    s=snapshot(data);r=s.roster.set_index('driver_id')
    assert r.loc['C','Submitted'] and r.loc['C','Days off group']=='Has days off'
    assert not r.loc['C','Own DVIR on day off']
    data[1]['appended_status_date']=['2026-11-23']
    assert snapshot(data).roster.set_index('driver_id').loc['C','Own DVIR on day off']


def test_training_review_uses_own_dated_submissions_and_ranks_recent_first():
    data=rows();data[0].update(PTITraining='Not done',totalPTI=None,count_vehicleID=None,
        count_trailerID=None,appended_startTIme=None,appended_endTime=None)
    for i in range(7):
        day=date(2026,11,22)-timedelta(days=i)
        data.append({'Tms_ID':f'TEST-T{i}','Samsara_DriverID':f'TEST-D{i}',
            'Samsara_DriverName':f'Example {i}','PTITraining':'Unknown','totalPTI':1,
            'appended_startTIme':[f'{day}T12:00:00Z'],'appended_endTime':[f'{day}T12:05:00Z']})
    s=snapshot(data);top=training_review_top_five(s)
    assert top.driver_id.tolist()==['C','TEST-D0','TEST-D1','TEST-D2','TEST-D3']
    r=s.roster.set_index('driver_id')
    assert r.loc['A','Submitted'] and not r.loc['A','Training not done with own DVIR']
    assert r.loc['A','pti_training_status']=='Not done'


def test_training_top_five_keeps_older_file_records_without_period_activity():
    data=rows();data[1].update(PTITraining='Not done',
        appended_startTIme=['2026-11-01T12:00:00Z'],appended_endTime=['2026-11-01T12:05:00Z'])
    s=snapshot(data);top=training_review_top_five(s)
    assert top.driver_id.tolist()==['C']
    assert top.iloc[0].dated_PTIs==0
    assert top.iloc[0]['Own dated DVIRs in file']==1
    assert top.iloc[0].last_done==date(2026,11,1)
    data[1].update(appended_startTIme=None,appended_endTime=None,totalPTI=2)
    assert training_review_top_five(snapshot(data)).empty  # Undated counts are not dated submissions.
    data[1].update(appended_startTIme=['2026-11-24T12:00:00Z'],appended_endTime=['2026-11-24T12:05:00Z'])
    assert training_review_top_five(snapshot(data)).empty  # As-of date excludes later records.
