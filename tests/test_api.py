import time

import pytest
from fastapi.testclient import TestClient

from app.graph_state import state
from app.main import app


@pytest.fixture(autouse=True)
def _clean():
    state.reset()
    state.set_background_flows(None)
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def optimize(client, **extra):
    return client.post("/api/v1/route/optimize", json={"origin": "NODO_A", "destination": "NODO_F", **extra})


def test_topology(client):
    r = client.get("/api/v1/topology").json()
    assert len(r["nodes"]) == 6 and r["active_events"] == []
    assert all(e["event"] == "NORMAL" for e in r["edges"])


def test_optimize_shape_and_latency(client):
    t = time.perf_counter()
    r = optimize(client)
    elapsed = (time.perf_counter() - t) * 1000
    assert r.status_code == 200, r.text
    body = r.json()
    tel = body["quantum_telemetry"]
    assert tel["qubits_used"] == 6 and len(tel["optimal_bitstring"]) == 6
    assert tel["feasible"] and tel["solver_used"] == "QAOA", tel
    assert body["optimized"]["route"][0] == "NODO_A" and body["optimized"]["route"][-1] == "NODO_F"
    assert body["selfish"]["route"] == ["NODO_A", "NODO_C", "NODO_D", "NODO_F"]
    assert elapsed < 500, f"latencia {elapsed:.0f} ms"


def test_one_hot(client):
    bits = optimize(client).json()["quantum_telemetry"]["optimal_bitstring"]
    assert all(bits[i:i + 2].count("1") == 1 for i in (0, 2, 4))


def test_accident_avoided(client):
    client.post("/api/v1/events/report", json={"source": "NODO_C", "target": "NODO_D", "event_type": "ACCIDENT"})
    body = optimize(client).json()
    route = body["optimized"]["route"]
    assert not any({a, b} == {"NODO_C", "NODO_D"} for a, b in zip(route, route[1:]))
    assert body["quantum_telemetry"]["feasible"]


def test_events_report_and_reset(client):
    r = client.post("/api/v1/events/report", json={"source": "NODO_B", "target": "NODO_D", "event_type": "TRAFFIC_JAM"}).json()
    e = next(e for e in r["edges"] if (e["source"], e["target"]) == ("NODO_B", "NODO_D"))
    assert e["current_time"] == pytest.approx(8 * 1.8) and e["current_penalty"] == pytest.approx(8 * 4)
    assert r["active_events"]
    r = client.post("/api/v1/events/reset").json()
    assert r["active_events"] == []


def test_accident_time(client):
    r = client.post("/api/v1/events/report", json={"source": "NODO_B", "target": "NODO_D", "event_type": "ACCIDENT"}).json()
    e = next(e for e in r["edges"] if (e["source"], e["target"]) == ("NODO_B", "NODO_D"))
    assert e["current_time"] == pytest.approx(5008.0)


def test_errors(client):
    assert client.post("/api/v1/events/report", json={"source": "NODO_A", "target": "NODO_F", "event_type": "ACCIDENT"}).status_code == 404
    assert optimize(client, origin="X").status_code in (404, 422)
    assert client.post("/api/v1/route/optimize", json={"origin": "NODO_A", "destination": "NODO_A"}).status_code == 422
    assert client.post("/api/v1/events/report", json={"source": "NODO_B", "target": "NODO_D", "event_type": "BOOM"}).status_code == 422


def test_custom_background_flows(client):
    bg = [{"origin": "NODO_C", "destination": "NODO_F", "vehicles": 40},
          {"origin": "NODO_B", "destination": "NODO_E", "vehicles": 10}]
    r = optimize(client, background_flows=bg)
    assert r.status_code == 200
    assert r.json()["flows"][1]["origin"] == "NODO_C"
