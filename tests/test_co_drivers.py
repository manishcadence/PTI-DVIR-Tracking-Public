from datetime import date

from src.analytics import driver_activity, shared_vehicles
from src.data_adapter import adapt
from src.filters import Filters, apply_filters, reporting_dates
from src.normalization import normalize


def test_signatures_team_mapping_and_shared_vehicles(dvir):
    dvir["secondSignature"] = {"signatoryUser": {"id": "D2", "name": "Alex"}}
    dvir["thirdSignature"] = {"signatoryUser": {"id": "M1", "name": "Mechanic"}}
    authored_by_partner = {**dvir, "id": "X2",
                           "authorSignature": {"signatoryUser": {"id": "D2", "name": "Alex"}}}
    data = normalize(adapt({"inspections": [dvir, authored_by_partner], "teamAssignments": [
        {"dvir_id": "X2", "driver_id": "D2", "co_driver_id": "D1"},
        {"dvir_id": "X1", "driver_id": "someone_else", "co_driver_id": "D2"},
    ]}), "UTC")
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 15)), Filters())
    assert len(data.dvir_signatures) == 6
    assert data.team_assignments.dvir_id.tolist() == ["X2"]
    assert data.team_assignments.co_driver_id.tolist() == ["D1"]
    assert shared_vehicles(scope.records).distinct_authors.tolist() == [2]
    assert driver_activity(scope).set_index("driver_id").submissions.to_dict() == {"D1": 1, "D2": 1}


def test_named_partner_without_id_is_retained(dvir):
    dvir["co_driver_name"] = "Jordan"
    data = normalize(adapt([dvir]), "UTC")
    assert data.team_assignments.co_driver_name.tolist() == ["Jordan"]
    assert data.team_assignments.co_driver_id.isna().all()


def test_cogo_columns_do_not_invent_confirmed_partners():
    grouped = {
        'driverID': 'D1', 'driverName': 'Author', 'totalPTI': 1,
        'tripTypes': ['preTrip'], 'startTimes': ['2026-11-15T12:00:00Z'],
        'cogoID_0': 'C1', 'driverName_0': 'Author',
        'cogoID_1': 'C2', 'driverName_1': 'Possible partner',
        'cogoID_2': 'C3', 'driverName_2': 'Another possible partner',
    }
    data = normalize(adapt([grouped]), 'UTC')
    assert data.team_assignments.empty
    assert not data.dvir_records.team_confirmed.any()
    assert data.dvir_records.iloc[0].raw['groupedSource']['cogoID_2'] == 'C3'


def test_ambiguous_and_self_team_candidates_stay_unconfirmed(dvir):
    data = normalize(adapt({'inspections': [dvir], 'teamAssignments': [
        {'dvir_id': 'X1', 'driver_id': 'D1', 'co_driver_id': 'D1'},
        {'dvir_id': 'X1', 'driver_id': 'D1', 'co_driver_id': 'D2'},
        {'dvir_id': 'X1', 'driver_id': 'D1', 'co_driver_id': 'D3'},
    ]}), 'UTC')
    assert data.team_assignments.empty
    assert not data.dvir_records.team_confirmed.any()


def test_confirmed_partner_never_receives_author_pti_credit(dvir):
    data = normalize(adapt({'inspections': [dvir, dvir],
                           'drivers': [{'id': 'D1'}, {'id': 'D2'}], 'rosterComplete': True,
                           'teamAssignments': [{'dvir_id': 'X1', 'driver_id': 'D1',
                                                'co_driver_id': 'D2'}]}), 'UTC')
    scope = apply_filters(data, reporting_dates(7, date(2026, 11, 15)), Filters())
    submissions = driver_activity(scope).set_index('driver_id').submissions
    assert submissions.to_dict() == {'D1': 1, 'D2': 0}
    assert len(data.team_assignments) == 1
