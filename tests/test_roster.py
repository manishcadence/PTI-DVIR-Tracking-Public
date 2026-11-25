from datetime import date
import json
import sqlite3
from src.data_adapter import adapt
from src.normalization import normalize
from src.filters import apply_filters, Filters, reporting_dates
from src.roster import roster_summary, roster_daily, roster_links
from src.roster_audit import roster_audit
from src.equipment import equipment_summary
from src.dvir_archive import archive_report


def roster_rows():
    common = {'vehicleID':'V1','vehicleName':'Truck One','tripTypes':['preTrip','postTrip'],
              'safetyStatuses':['safe'],'startTimes':['2026-11-19T12:00:00Z','2026-11-20T12:00:00Z'],
              'endTimes':['2026-11-19T12:10:00Z','2026-11-20T12:10:00Z'],'totalPTI':2,
              'driverID':'A','driverName':'Author','cogoID_0':'CA','driverName_0':'Author',
              'cogoID_1':'CR','driverName_1':'Roster Partner'}
    return [{**common,'Tms_ID':'TR','Samsara_DriverID':'R','Samsara_DriverName':'Roster Partner',
             'COGOELD':'CR','matched_on':'cogoID_1','count_status_date':2,
             'appended_status_date':'2026-11-19, 2026-11-20'},
            {**common,'Tms_ID':'TA','Samsara_DriverID':'A','Samsara_DriverName':'Author',
             'COGOELD':'CA','PTITraining':'Done'},
            {'Tms_ID':'TC','Tms_driverName':'No matched ID','Samsara_DriverID':None,
             'totalPTI':None,'startTimes':None,'endTimes':None}]


def test_joined_roster_keeps_unmatched_drivers_and_separates_authors():
    data = normalize(adapt(roster_rows()),'America/Chicago')
    assert set(data.drivers.driver_id)=={'R','A','tms:TC'}
    assert len(data.dvir_records)==2
    assert set(data.dvir_records.author_id)=={'A'}
    dates=reporting_dates(7,date(2026,11,20))
    summary=roster_summary(data,dates,dates[-1]).set_index('driver_id')
    assert summary.loc['R','PTI_records']==0
    assert summary.loc['R','availability']=='On holiday'
    assert summary.loc['R','nonholiday_dates_without_PTI']==5
    assert summary.loc['A','PTI_records']==2
    assert summary.loc['tms:TC','needs_samsara_id']
    assert set(apply_filters(data,dates,Filters()).drivers.driver_id)=={'R','A','tms:TC'}
    links=roster_links(data,dates)
    partner=links[links.driver_id.eq('R')].iloc[0]
    assert partner.partner_id=='A' and partner.driver_own_PTIs==0 and partner.partner_own_PTIs==2
    daily=roster_daily(data,dates).iloc[-1]
    assert daily.on_holiday==1 and daily.available==2 and daily.drivers_with_own_PTI==1
    equipment=equipment_summary(data.dvir_records,data.source_rows).set_index('driver_id')
    assert equipment.loc['R','vehicle_names']=='Truck One'


def test_roster_archive_keeps_snapshots_and_id_checks(tmp_path):
    envelope=adapt(roster_rows())
    data=normalize(envelope,'America/Chicago')
    issues=roster_audit(data)
    assert 'Missing Samsara ID' in set(issues.check)
    assert 'Separate co-driver author' in set(issues.check)
    assert 'Repeated joined inspection history' in set(issues.check)
    path=tmp_path/'history.sqlite3'
    archive_report(path,tmp_path/'backups',envelope,'roster.json')
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM roster_snapshots').fetchone()[0]==3
        assert conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]==2


def test_author_outside_roster_does_not_enlarge_tracked_roster():
    rows=roster_rows()[:1]
    data=normalize(adapt(rows),'America/Chicago')
    dates=reporting_dates(7,date(2026,11,20))
    scope=apply_filters(data,dates,Filters())
    assert scope.drivers.driver_id.tolist()==['R']
    assert set(data.dvir_records.author_id)=={'A'}
    summary=roster_summary(data,dates,dates[-1])
    assert summary.PTI_records.sum()==0



def test_identity_audit_flags_name_join_and_license_conflict_without_changing_ids():
    rows=roster_rows()
    rows[0].update(MatchReason='MondayfullName',Tms_licenseNumber='AB-123',Samsara_licenseNumber='ZZ999')
    data=normalize(adapt(rows),'America/Chicago')
    issues=roster_audit(data)
    assert 'Name-based roster identity crosswalk' in set(issues.check)
    assert 'TMS and Samsara license values differ' in set(issues.check)
    summary=roster_summary(data,reporting_dates(7,date(2026,11,20)),date(2026,11,20)).set_index('driver_id')
    assert summary.loc['R','identity_review']
    assert set(data.drivers.driver_id)=={'R','A','tms:TC'}
    assert set(data.dvir_records.author_id)=={'A'}
