from datetime import date, timedelta
from io import BytesIO
import json
from copy import deepcopy
from openpyxl import load_workbook
from src.upload_model import parse_upload
from src.stakeholder_report import build_stakeholder_report, excel_bytes, SHEETS
from test_upload_model import rows


def build(data=None, end=date(2026,11,23)):
    # Report-shape tests use trained roster fixtures; explicit statuses remain unchanged.
    data=deepcopy(rows() if data is None else data)
    for row in data:
        if row.get('Tms_ID'):row.setdefault('PTITraining','DONE')
    return build_stakeholder_report(parse_upload(json.dumps(data).encode()), end, 'report.json')


def test_simple_report_is_fifteen_days_and_roster_scoped():
    r=build()
    assert r.start==date(2026,11,9) and r.end==date(2026,11,23)
    assert r.roster_count==3 and r.co_roster_count==1
    assert r.tables['Solo with DVIR']['Driver ID'].tolist()==['C']
    assert r.tables['Solo without DVIR']['Driver ID'].tolist()==['D']
    assert r.tables['No PTI in entire file']['Driver ID'].tolist()==['D']
    team=r.tables['Co-driver with DVIR'].iloc[0]
    assert team['Driver names']=='Alice\nBob'
    assert team['DVIRs by driver']=='Alice: 2\nBob: 1'
    assert team['DVIRs (15 days)']==3 and team['Status']=='Submitted'


def test_either_partner_submitting_excludes_primary_from_not_done():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None)
    r=build(data)
    assert 'A' not in set(r.tables['No PTI in entire file']['Driver ID'])
    assert r.tables['Co-driver with DVIR'].iloc[0]['DVIRs by driver']=='Alice: 0\nBob: 1'


def test_holiday_training_and_missing_dates_are_separate_from_no_dvir():
    data=rows();data[2].update(count_status_date=15,appended_status_date=[(date(2026,11,23)-timedelta(days=i)).isoformat() for i in range(15)])
    r=build(data)
    assert r.tables['No PTI in entire file']['Driver ID'].tolist()==['D']
    assert r.tables['Solo without DVIR'].iloc[0]['Status']=='Day off'
    data[2].update(count_status_date=0,appended_status_date=[],PTITraining='DONE',PTITrainingDate='2026-11-24')
    r=build(data)
    assert r.tables['No PTI in entire file']['Driver ID'].tolist()==['D']
    assert 'Trained after period' in r.tables['Solo without DVIR'].iloc[0]['Status']
    data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-01',totalPTI=2)
    r=build(data)
    assert r.tables['No PTI in entire file'].empty
    assert r.tables['Solo without DVIR'].iloc[0]['Status']=='Review inspection dates'


def test_period_boundary_and_vehicle_context_without_dvir():
    data=rows();data[1].update(totalPTI=2,appended_startTIme=['2026-11-08T23:59:00-06:00','2026-11-09T00:00:00-06:00'],
        appended_endTime=['2026-11-08T23:59:30-06:00','2026-11-09T00:05:00-06:00'])
    data[2]['vehicleName']='Truck 99'
    r=build(data)
    assert r.tables['Solo with DVIR'].iloc[0]['DVIRs (15 days)']==1
    assert r.tables['Solo with DVIR'].iloc[0]['Last DVIR']==date(2026,11,9)
    assert r.tables['Solo without DVIR'].iloc[0]['Vehicles']=='Truck 99'
    assert r.tables['Solo without DVIR'].iloc[0]['DVIRs (15 days)']==0


def test_neither_member_submitting_and_extra_unmapped_member_are_retained():
    data=rows();data[0].update(totalPTI=None,count_vehicleID=None,count_trailerID=None,appended_startTIme=None,appended_endTime=None,
        CODRIVER_totalPTI=None,CODRIVER_count_vehicleID=None,CODRIVER_count_trailerID=None,CODRIVER_appended_startTIme=None,
        CODRIVER_appended_endTime=None,cogoID_2='CC',driverName_2='Charlie')
    r=build(data)
    assert set(r.tables['No PTI in entire file']['Driver ID'])=={'A','D'}
    assert r.tables['Co-driver without DVIR'].iloc[0]['Status']=='No DVIR'
    assert 'Charlie' in r.tables['Co-driver without DVIR'].iloc[0]['Other crew']


def test_excel_roundtrip_ids_dates_filters_panes_and_literal_text():
    data=rows();data[1].update(Tms_ID='000123',Samsara_DriverName='=1+1')
    r=build(data);book=load_workbook(BytesIO(excel_bytes(r)),data_only=False)
    assert book.sheetnames==[name for name,_ in SHEETS]
    sheet=book['Solo with DVIR']
    assert sheet['A7'].value=='000123' and sheet['A7'].data_type=='s'
    assert sheet['C7'].value=='=1+1' and sheet['C7'].data_type=='s'
    assert sheet['F7'].value==1 and sheet['F7'].data_type=='n'
    assert sheet['G7'].value.date()==date(2026,11,23)
    assert sheet.freeze_panes=='B7'
    assert sheet.auto_filter.ref=='A6:K7'
    assert sheet.sheet_view.showGridLines is False
    assert len(sheet.conditional_formatting)==2
    assert book['Co-driver with DVIR']['B7'].value=='Alice\nBob'


def test_training_during_period_with_all_post_training_dates_on_holiday():
    data=rows();data[2].update(PTITraining='DONE',PTITrainingDate='2026-11-20',count_status_date=3,
        appended_status_date=['2026-11-21','2026-11-22','2026-11-23'])
    r=build(data)
    assert r.tables['No PTI in entire file']['Driver ID'].tolist()==['D']
    assert r.tables['Solo without DVIR'].iloc[0]['Status']=='Day off'


def test_no_roster_still_exports_five_valid_empty_tables():
    r=build([{'driverID':'X','driverName':'Unmatched','totalPTI':0}])
    assert r.roster_count==0 and all(frame.empty for frame in r.tables.values())
    book=load_workbook(BytesIO(excel_bytes(r)))
    assert len(book.worksheets)==5


def test_four_period_groups_and_no_pti_in_file_are_distinct():
    data=rows();data[0].update(appended_startTIme=['2026-10-01T12:00:00Z'],appended_endTime=['2026-10-01T12:05:00Z'],
        CODRIVER_totalPTI=None,CODRIVER_count_vehicleID=None,CODRIVER_count_trailerID=None,CODRIVER_appended_startTIme=None,CODRIVER_appended_endTime=None)
    r=build(data)
    assert r.tables['Co-driver with DVIR'].empty
    team=r.tables['Co-driver without DVIR'].iloc[0]
    assert team['Driver names']=='Alice\nBob' and team['DVIRs (15 days)']==0
    assert team['Last DVIR']==date(2026,10,1)
    assert r.tables['No PTI in entire file']['Driver ID'].tolist()==['D']
    assert set(r.tables['Solo with DVIR']['Driver ID']) | set(r.tables['Solo without DVIR']['Driver ID'])=={'C','D'}


def test_supplied_safety_is_kept_separate_for_each_author_and_missing_is_not_safe():
    data=rows();data[0]['safetyStatuses']=['safe','resolved','unsafe'];data[0]['CODRIVER_safetyStatuses']=['resolved']
    data[1]['appended_safetyStatus']=['safe']
    r=build(data)
    assert r.tables['Solo with DVIR'].iloc[0]['Safety status (file)']=='Safe'
    assert r.tables['Solo without DVIR'].iloc[0]['Safety status (file)']=='Not supplied'
    safety=r.tables['Co-driver with DVIR'].iloc[0]['Safety by driver (file)']
    assert safety=='Alice: Unsafe\nBob: Resolved'
    book=load_workbook(BytesIO(excel_bytes(r)))
    assert book['Solo with DVIR']['K7'].value=='Safe'


def test_days_off_labels_in_tables_and_excel_keep_the_same_counts():
    r=build()
    assert r.tables['Solo without DVIR']['Days off'].tolist()==[1]
    assert 'Days off by driver' in r.tables['Co-driver with DVIR'].columns
    assert all('Holiday days' not in frame.columns for frame in r.tables.values())
    book=load_workbook(BytesIO(excel_bytes(r)))
    assert 'Days off' in [cell.value for cell in book['Solo without DVIR'][6]]
    assert 'Days off by driver' in [cell.value for cell in book['Co-driver with DVIR'][6]]


def test_not_done_drivers_are_excluded_from_solo_and_entire_file_reports_but_retained():
    from src.upload_model import people_summary
    data=rows();data[1]['PTITraining']='Unknown';data[2]['PTITraining']=None
    raw=parse_upload(json.dumps(data).encode())
    report=build_stakeholder_report(raw,date(2026,11,23),'report.json')
    assert report.tables['Solo with DVIR'].empty
    assert report.tables['Solo without DVIR'].empty
    assert report.tables['No PTI in entire file'].empty
    assert not report.tables['Co-driver with DVIR'].empty
    summary=people_summary(raw,[date(2026,11,23)-timedelta(days=i) for i in range(15)],date(2026,11,23))
    assert set(summary.loc[summary.in_roster & summary.pti_training_status.eq('Not done'),'driver_id'])=={'C','D'}


def test_entire_file_needs_training_done_and_neither_member_recorded():
    data=rows();data[1]['PTITraining']='DONE';data[2]['PTITraining']='DONE'
    report=build_stakeholder_report(parse_upload(json.dumps(data).encode()),date(2026,11,23),'report.json')
    assert report.tables['Solo with DVIR']['Driver ID'].tolist()==['C']
    assert report.tables['Solo without DVIR']['Driver ID'].tolist()==['D']
    assert report.tables['No PTI in entire file']['Driver ID'].tolist()==['D']
    book=load_workbook(BytesIO(excel_bytes(report)))
    for name in ('Solo with DVIR','Solo without DVIR','No PTI in entire file'):
        header=[cell.value for cell in book[name][6]]
        training_col=header.index('PTI training')
        assert all(row[training_col]=='Done' for row in book[name].iter_rows(min_row=7,values_only=True))


def test_days_off_categories_and_older_file_history_are_independent():
    data=rows()
    data[1].update(appended_startTIme=['2026-11-01T14:00:00Z'],
                   appended_endTime=['2026-11-01T14:05:00Z'],
                   count_status_date=0,appended_status_date=[])
    data.append({'Tms_ID':'TE','Samsara_DriverID':'E','Samsara_DriverName':'Evan'})
    r=build(data)
    solo=r.tables['Solo without DVIR'].set_index('Driver ID')
    assert solo.loc['C','DVIR history']=='Has records in file'
    assert solo.loc['C','Last DVIR']==date(2026,11,1)
    assert solo.loc['C','Days off category']=='No days off reported'
    assert solo.loc['C','Days off']==0
    assert solo.loc['D','Days off category']=='Has days off'
    assert solo.loc['D','DVIR history']=='No record in entire file'
    assert solo.loc['E','Days off category']=='No days off reported'
    assert solo.loc['E','Days off']=='Not supplied'
    assert set(r.tables['No PTI in entire file']['Driver ID'])=={'D','E'}
    book=load_workbook(BytesIO(excel_bytes(r)))
    assert 'DVIR history' in [cell.value for cell in book['Solo without DVIR'][6]]
    assert 'Days off category' in [cell.value for cell in book['No PTI in entire file'][6]]


def test_mixed_report_display_serializes_to_arrow_without_changing_exports():
    import pyarrow as pa
    from src.components.tables import display_frame
    data=rows()
    data[1].update(appended_startTIme=['2026-11-01T14:00:00Z'],
                   appended_endTime=['2026-11-01T14:05:00Z'])
    r=build(data)
    original=r.tables['Solo without DVIR']
    visible=display_frame(original,text_columns=('Days off',))
    pa.Table.from_pandas(visible,preserve_index=False)
    assert visible['Days off'].tolist()==['Not supplied','1']
    assert original['Days off'].tolist()==['Not supplied',1]
    assert display_frame(original.iloc[[1]],text_columns=('Days off',))['Days off'].tolist()==['1']
    book=load_workbook(BytesIO(excel_bytes(r)))
    sheet=book['Solo without DVIR']
    headers=[cell.value for cell in sheet[6]]
    assert sheet.cell(8,headers.index('Days off')+1).value==1
