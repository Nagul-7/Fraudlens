"""
Role-based data segregation, proved over HTTP.

The deck says data is separated by role on the server, and that a bank is given
no crime intelligence. These tests are what make that a checked property and not
just a sentence: each one calls the real API as a given role and asserts on what
comes back.

What the prototype can and cannot promise. There is no login, so the role is
asserted by the caller. What the server guarantees is that a response never
contains more than the asserted role is entitled to. In production the role would
come from an authenticated identity instead of a query parameter.

Run from anywhere:  pytest tests/
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app

N_DISTRICTS = 724
BANKS = ["Axis", "SBI", "HDFC"]
STATES = ["Jharkhand", "West Bengal", "Goa"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:          # runs the startup hook: model, data, holdings
        yield c


@pytest.fixture(autouse=True)
def fresh_clock(client):
    """Every test starts at the first test window with an empty alert feed."""
    client.post("/simulate/reset")
    yield
    client.post("/simulate/reset")


def get_ids(resp):
    return {d["district_id"] for d in resp.json()["districts"]}


@pytest.fixture(scope="module")
def state_of(client):
    """district_id -> state, read from the GeoJSON the dashboard itself uses."""
    feats = client.get("/geojson/districts").json()["features"]
    return {f["properties"]["district_id"]: f["properties"]["state"] for f in feats}


# --------------------------------------------------------------- /heatmap: STATE
@pytest.mark.parametrize("state", STATES)
def test_state_heatmap_returns_only_that_state(client, state_of, state):
    r = client.get("/heatmap", params={"role": "STATE", "state_name": state})
    assert r.status_code == 200
    ids = get_ids(r)
    assert ids, "a State LEA must see its own districts"
    assert {state_of[i] for i in ids} == {state}
    # ...and all of them: scoping must not silently drop the state's own districts
    assert len(ids) == sum(1 for s in state_of.values() if s == state)


def test_jharkhand_lea_gets_exactly_jharkhands_24_districts(client):
    r = client.get("/heatmap", params={"role": "STATE", "state_name": "Jharkhand"})
    body = r.json()
    assert body["n_districts"] == 24
    assert {d["state"] for d in body["districts"]} == {"Jharkhand"}


def test_state_filter_can_never_widen_a_state_role(client):
    widen = client.get("/heatmap", params={"role": "STATE", "state_name": "Jharkhand", "state": "Bihar"})
    assert widen.status_code == 403
    same = client.get("/heatmap", params={"role": "STATE", "state_name": "Jharkhand", "state": "Jharkhand"})
    assert same.status_code == 200 and same.json()["n_districts"] == 24


def test_state_role_needs_a_jurisdiction(client):
    assert client.get("/heatmap", params={"role": "STATE"}).status_code == 400
    assert client.get("/heatmap", params={"role": "STATE", "state_name": "Atlantis"}).status_code == 404


# --------------------------------------------------------------- /heatmap: BANK
@pytest.mark.parametrize("bank", BANKS)
def test_bank_heatmap_is_exactly_the_banks_footprint(client, bank):
    """The heatmap and /bank/exposure share one footprint definition."""
    heat = client.get("/heatmap", params={"role": "BANK", "bank": bank})
    expo = client.get("/bank/exposure", params={"bank": bank})
    assert heat.status_code == 200 and expo.status_code == 200
    footprint = set(expo.json()["own_district_ids"])
    assert get_ids(heat) == footprint
    assert 0 < len(footprint) < N_DISTRICTS, "a bank must not see the whole country"


def test_bank_heatmap_carries_no_crime_intelligence(client):
    """Only id, name, state and score. No national rank, no active-chain counts."""
    r = client.get("/heatmap", params={"role": "BANK", "bank": "Axis"})
    for d in r.json()["districts"]:
        assert set(d) == {"district_id", "risk", "name", "state"}


def test_bank_state_filter_narrows_and_never_leaves_the_footprint(client, state_of):
    footprint = set(client.get("/bank/exposure", params={"bank": "Axis"}).json()["own_district_ids"])
    r = client.get("/heatmap", params={"role": "BANK", "bank": "Axis", "state": "Bihar"})
    ids = get_ids(r)
    assert ids and ids <= footprint
    assert {state_of[i] for i in ids} == {"Bihar"}


def test_bank_with_nothing_in_a_state_gets_an_empty_result_not_national_data(client):
    r = client.get("/heatmap", params={"role": "BANK", "bank": "Axis", "state": "Sikkim"})
    assert r.status_code == 200
    assert r.json()["n_districts"] == 0 and r.json()["districts"] == []


def test_bank_role_needs_a_real_bank(client):
    assert client.get("/heatmap", params={"role": "BANK"}).status_code == 400
    assert client.get("/heatmap", params={"role": "BANK", "bank": "NoSuchBank"}).status_code == 404


# ------------------------------------------------------------- /heatmap: I4C
def test_i4c_and_no_role_still_see_every_district_with_real_scores(client):
    for params in ({"role": "I4C"}, {}):
        body = client.get("/heatmap", params=params).json()
        assert body["n_districts"] == N_DISTRICTS
        assert all(d["risk"] is not None for d in body["districts"])
        assert all({"rank", "active_chains"} <= set(d) for d in body["districts"])
    assert client.get("/heatmap", params={"state": "Jharkhand"}).json()["n_districts"] == 24


# ------------------------------------------------- /districts/{id}: drill-down
def test_district_detail_is_scoped_by_role(client, state_of):
    jh = next(i for i, s in state_of.items() if s == "Jharkhand")
    wb = next(i for i, s in state_of.items() if s == "West Bengal")
    lea = {"role": "STATE", "state_name": "Jharkhand"}
    assert client.get(f"/districts/{jh}", params=lea).status_code == 200
    assert client.get(f"/districts/{wb}", params=lea).status_code == 403      # out of jurisdiction
    assert client.get(f"/districts/{jh}", params={"role": "BANK", "bank": "Axis"}).status_code == 403
    assert client.get(f"/districts/{wb}", params={"role": "I4C"}).status_code == 200
    assert client.get(f"/districts/{wb}").status_code == 200


def test_a_refused_drilldown_carries_no_intelligence(client, state_of):
    wb = next(i for i, s in state_of.items() if s == "West Bengal")
    r = client.get(f"/districts/{wb}", params={"role": "STATE", "state_name": "Jharkhand"})
    assert r.status_code == 403
    assert "reason_codes" not in r.text and "live_chains" not in r.text


# ------------------------------------------------------------------- /alerts
def test_alerts_are_refused_to_banks_and_scoped_for_states(client):
    assert client.get("/alerts", params={"role": "BANK", "bank": "Axis"}).status_code == 403
    r = client.get("/alerts", params={"role": "STATE", "state_name": "Jharkhand", "threshold": 0.0})
    alerts = r.json()["alerts"]
    assert alerts and {a["state"] for a in alerts} == {"Jharkhand"}
    national = client.get("/alerts", params={"threshold": 0.0, "limit": 200}).json()["alerts"]
    assert len({a["state"] for a in national}) > 1


def test_alerts_state_filter_is_actually_applied(client):
    """The `state` param used to be declared and silently ignored."""
    alerts = client.get("/alerts", params={"threshold": 0.0, "state": "Bihar"}).json()["alerts"]
    assert alerts and {a["state"] for a in alerts} == {"Bihar"}


# --------------------------------------------------------- POST /simulate/advance
def test_advance_scopes_its_district_level_payload(client):
    """The dashboard calls advance under every role, so it must not leak either."""
    bank = client.post("/simulate/advance", params={"threshold": 0.5, "role": "BANK", "bank": "Axis"}).json()
    assert bank["new_alerts"] == []
    assert bank["now"]["top_districts"] == []
    assert bank["previous_window"] is None            # national cash-out counts: withheld

    client.post("/simulate/reset")
    lea = client.post("/simulate/advance",
                      params={"threshold": 0.5, "role": "STATE", "state_name": "Jharkhand"}).json()
    assert {a["state"] for a in lea["new_alerts"]} <= {"Jharkhand"}
    assert {t["state"] for t in lea["now"]["top_districts"]} <= {"Jharkhand"}
    assert lea["now"]["top_districts"], "the state's own top districts should still be reported"

    client.post("/simulate/reset")
    i4c = client.post("/simulate/advance", params={"threshold": 0.5}).json()
    assert len({a["state"] for a in i4c["new_alerts"]}) > 1
    assert len({t["state"] for t in i4c["now"]["top_districts"]}) > 1
    assert i4c["previous_window"] is not None


# ------------------------------- the endpoints that were already role-aware
def test_existing_role_endpoints_still_hold(client, state_of):
    client.post("/simulate/advance", params={"threshold": 0.5})
    assert client.get("/feed", params={"role": "BANK", "bank": "Axis"}).json()["alerts"] == []
    lea = client.get("/feed", params={"role": "STATE", "state_name": "Jharkhand"}).json()["alerts"]
    assert {a["state"] for a in lea} <= {"Jharkhand"}
    expo = client.get("/bank/exposure", params={"bank": "Axis", "state_name": "Goa"}).json()
    assert {r["state"] for r in expo["atm_exposure"] + expo["accounts_holding"]} <= {"Goa"}
    assert {state_of[i] for i in expo["own_district_ids"]} <= {"Goa"}
