"""Orquestación: QAOA vs. ruta egoísta clásica (Dijkstra) y métricas."""
from __future__ import annotations

import time

import networkx as nx

from . import config
from .graph_state import GraphState, QNavError, edge_key, path_edges
from .qubo_builder import Flow, build_qubo, pair_weight, path_time, shared_penalty
from .schemas import OptimizeRequest
from .solver import solve


def _validate_nodes(graph: nx.Graph, *nodes: str) -> None:
    for n in nodes:
        if n not in graph:
            raise QNavError(404, f"Nodo desconocido: {n}")


def _resolve_flows(graph: nx.Graph, req: OptimizeRequest, state: GraphState) -> list[Flow]:
    bg = (
        [f.model_dump() for f in req.background_flows] if req.background_flows
        else state.background_flows or config.DEFAULT_BACKGROUND_FLOWS
    )
    specs = [("usuario", req.origin, req.destination, req.vehicles)]
    specs += [(f"fondo_{i}", f["origin"], f["destination"], f["vehicles"]) for i, f in enumerate(bg, 1)]
    flows = []
    for idx, (name, o, d, v) in enumerate(specs):
        _validate_nodes(graph, o, d)
        if o == d:
            raise QNavError(422, f"El flujo {name} tiene origen y destino iguales")
        flows.append(Flow(idx, name, o, d, v))
    return flows


def _evaluate(graph: nx.Graph, flows: list[Flow], paths: list[list[str]]) -> dict:
    """Métricas del usuario, costo del sistema y carga por arista para una asignación."""
    per_flow = []
    for i, f in enumerate(flows):
        cong = sum(
            shared_penalty(graph, paths[i], paths[j], pair_weight(f, flows[j]))
            for j in range(len(flows)) if j != i
        )
        tt = path_time(graph, paths[i])
        per_flow.append({"travel_time": tt, "congestion_penalty": cong, "estimated_time": tt + cong})

    loads: dict = {edge_key(u, v): 0 for u, v in graph.edges}
    for f, p in zip(flows, paths):
        for e in path_edges(p):
            loads[e] += f.vehicles
    return {
        "per_flow": per_flow,
        "system_cost": sum(m["estimated_time"] for m in per_flow),
        "loads": loads,
    }


def _metrics(paths: list[str], m: dict) -> dict:
    return {
        "route": paths,
        "travel_time": round(m["travel_time"], 3),
        "congestion_penalty": round(m["congestion_penalty"], 3),
        "estimated_time": round(m["estimated_time"], 3),
    }


def _pct(old: float, new: float) -> float:
    return round((old - new) / old * 100, 2) if old else 0.0


def optimize(req: OptimizeRequest, state: GraphState) -> dict:
    t0 = time.perf_counter()
    graph = state.snapshot()
    _validate_nodes(graph, req.origin, req.destination)
    flows = _resolve_flows(graph, req, state)

    model = build_qubo(graph, flows)
    outcome = solve(model.program)

    # Decodifica: un flujo -> la ruta k con x_{i,k} = 1
    chosen = []
    for f in flows:
        bits = outcome.x[f.index * config.K_ROUTES:(f.index + 1) * config.K_ROUTES]
        chosen.append(model.candidates[f.index][bits.index(1) if 1 in bits else 0])

    # Línea base: todos egoístas (Dijkstra por tiempo, sin ver la congestión cruzada)
    selfish = [nx.dijkstra_path(graph, f.origin, f.destination, weight="time") for f in flows]

    q_eval = _evaluate(graph, flows, chosen)
    s_eval = _evaluate(graph, flows, selfish)
    state.set_loads(q_eval["loads"])

    edge_loads = []
    for u, v, d in graph.edges(data=True):
        k = edge_key(u, v)
        cap = d["capacity"]
        edge_loads.append({
            "source": k[0], "target": k[1], "capacity": cap, "event": d["event"],
            "vehicles_optimized": q_eval["loads"][k],
            "saturation_optimized": round(q_eval["loads"][k] / cap, 4),
            "vehicles_selfish": s_eval["loads"][k],
            "saturation_selfish": round(s_eval["loads"][k] / cap, 4),
        })

    qu, su = q_eval["per_flow"][0], s_eval["per_flow"][0]
    return {
        "origin": req.origin,
        "destination": req.destination,
        "optimized": _metrics(chosen[0], qu),
        "selfish": _metrics(selfish[0], su),
        "comparison": {
            "user_time_saved": round(su["estimated_time"] - qu["estimated_time"], 3),
            "user_improvement_pct": _pct(su["estimated_time"], qu["estimated_time"]),
            "system_cost_optimized": round(q_eval["system_cost"], 3),
            "system_cost_selfish": round(s_eval["system_cost"], 3),
            "system_improvement_pct": _pct(s_eval["system_cost"], q_eval["system_cost"]),
        },
        "flows": [
            {"name": f.name, "origin": f.origin, "destination": f.destination, "vehicles": f.vehicles,
             "qaoa_route": chosen[f.index], "selfish_route": selfish[f.index]}
            for f in flows
        ],
        "edge_loads": edge_loads,
        "quantum_telemetry": {
            "qubits_used": len(model.var_names),
            "optimal_bitstring": outcome.bitstring,
            "variables": model.var_names,
            "top_probabilities": outcome.top_probabilities,
            "execution_time_ms": outcome.execution_time_ms,
            "solver_used": outcome.solver_used,
            "feasible": outcome.feasible,
            "qubo_scale": round(model.scale, 5),
            "note": outcome.note,
        },
        "total_time_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
