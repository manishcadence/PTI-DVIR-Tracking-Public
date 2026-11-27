import json
from datetime import date

from src.upload_model import parse_upload
from src.tracking_overview import tracking_snapshot
from test_upload_model import rows


def reviewed(data):
    return tracking_snapshot(parse_upload(json.dumps(data).encode()),date(2026,11,23)).roster.set_index('driver_id')


def test_driver_source_findings_and_followup_actions_are_attached():
    data=rows();data[1]['totalPTI']=4
    r=reviewed(data)
    assert r.loc['C','source_review_items']>0
    assert 'Reported count differs from timestamps' in r.loc['C','data_checks']
    assert r.loc['C','review_category']=='Source data review'
    assert 'training record' in r.loc['C','suggested_next_step']
    assert 'Reported PTI' in r.loc['C','check_details']


def test_linked_codriver_findings_are_named_without_affecting_unrelated_drivers():
    data=rows();data[0]['CODRIVER_totalPTI']=5
    r=reviewed(data)
    assert r.loc['A','source_review_items']>0
    assert 'Co-driver Bob:' in r.loc['A','data_checks']
    assert r.loc['C','source_review_items']==0
    assert 'Bob' not in r.loc['C','data_checks']


def test_tracking_reason_and_next_step_keep_days_off_and_training_context():
    data=rows();data[2]['PTITraining']='DONE'
    r=reviewed(data)
    assert r.loc['D','review_category']=='Submission follow-up'
    assert 'days actually worked' in r.loc['D','suggested_next_step']
    assert 'No own or linked co-driver submission' in r.loc['D','data_checks']
    assert r.loc['C','review_category']=='Training record review'
    assert 'inspection submission does not establish training completion' in r.loc['C','suggested_next_step']


def test_informational_source_notes_do_not_become_source_review_flags():
    r=reviewed(rows())
    assert r.loc['A','source_review_items']==0
    assert r.loc['A','review_category']=='Source information'
    assert 'Informational source notes' in r.loc['A','suggested_next_step']
