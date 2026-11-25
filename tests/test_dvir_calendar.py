"""Calendar must distinguish absent records, holidays, and recorded review activity."""
from datetime import date
import pandas as pd
from src.components.dvir_calendar import calendar_figure


def fixture():
    days=[date(2026,11,n) for n in (21,22,23)]
    people=pd.DataFrame([dict(driver_name='Same name', driver_id='A', vehicle_names='Truck 7', holidays={days[0],days[1]}),
                         dict(driver_name='Same name', driver_id='B', vehicle_names='Truck 7', holidays=set())])
    events=pd.DataFrame([dict(driver_id='A',inspection_date=days[0],record_key='1',needs_review=False),
                         dict(driver_id='A',inspection_date=days[0],record_key='2',needs_review=False),
                         dict(driver_id='B',inspection_date=days[2],record_key='3',needs_review=True)])
    return people,events,days


def test_calendar_preserves_own_counts_holiday_and_review_states():
    people,events,days=fixture()
    fig=calendar_figure(people,events,days)
    trace=fig.data[0]
    assert list(trace.z[0])==[1,3,0]
    assert list(trace.z[1])==[0,0,2]
    assert list(trace.text[0])==['2<br>DVIRs*','Day off','No DVIR']
    assert trace.text[1][2]=='1<br>Review'
    assert 'data review needed' in trace.customdata[1][2]
    assert 'day off (DVIR retained)' in trace.customdata[0][0]
    assert 'Vehicles in report: Truck 7' in trace.customdata[0][0]


def test_calendar_separates_cells_and_identifies_same_name_drivers():
    people,events,days=fixture()
    fig=calendar_figure(people,events,days)
    assert fig.data[0].xgap>=2 and fig.data[0].ygap>=2
    assert fig.data[0].showscale is False
    assert fig.layout.xaxis.side=='top'
    assert 'ID A' in fig.layout.yaxis.ticktext[0]
    assert 'ID B' in fig.layout.yaxis.ticktext[1]
    assert fig.layout.yaxis.autorange=='reversed'
    assert fig.layout.xaxis.fixedrange and fig.layout.yaxis.fixedrange


def test_before_training_cells_are_not_marked_no_dvir_and_records_are_preserved():
    people,events,days=fixture()
    people['training_completed_date']=date(2026,11,22)
    people['pti_training_status']='Done'
    fig=calendar_figure(people,events,days)
    assert fig.data[0].text[1][0]=='Before<br>training'
    assert fig.data[0].text[1][1]=='Training<br>date'
    assert fig.data[0].text[1][2]=='1<br>Review'
    assert fig.data[0].text[0][0]=='2<br>DVIRs*'
