"""Construcción del QuadraticProgram (QUBO) a partir de rutas candidatas."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice

import networkx as nx
from qiskit_optimization import QuadraticProgram

from . import config
from .graph_state import EdgeKey, SuperposeError, path_edges


@dataclass(frozen=True)
class Flow:
    index: int
    name: str
    origin: str
    destination: str
    vehicles: int


@dataclass
class QuboModel:
    program: QuadraticProgram
    flows: list[Flow]
    candidates: list[list[list[str]]]   # [flujo][k] -> camino (lista de nodos)
    var_names: list[str]                # orden de qubits
    scale: float


def var_name(flow_idx: int, k: int) -> str:
    return f"x_{flow_idx}_{k}"


def candidate_paths(graph: nx.Graph, flow: Flow) -> list[list[str]]:
    """K rutas simples más cortas; si hay menos de K se repite la mejor (relleno)."""
    try:
        paths = list(islice(nx.shortest_simple_paths(graph, flow.origin, flow.destination, weight="time"),
                            config.K_ROUTES))
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise SuperposeError(422, f"No hay ruta entre {flow.origin} y {flow.destination}") from exc
    while len(paths) < config.K_ROUTES:
        paths.append(list(paths[0]))
    return paths


def path_time(graph: nx.Graph, path: list[str]) -> float:
    return sum(graph[a][b]["time"] for a, b in zip(path, path[1:]))


def pair_weight(f_i: Flow, f_j: Flow) -> float:
    """Peso de congestión entre dos flujos: proporcional al volumen conjunto."""
    return (f_i.vehicles + f_j.vehicles) / config.VEHICLES_REF


def shared_penalty(graph: nx.Graph, path_i: list[str], path_j: list[str], w: float) -> float:
    """Σ_e P_e · w sobre las aristas compartidas por ambas rutas."""
    shared: set[EdgeKey] = set(path_edges(path_i)) & set(path_edges(path_j))
    return sum(graph[u][v]["penalty"] for u, v in shared) * w


def build_qubo(graph: nx.Graph, flows: list[Flow]) -> QuboModel:
    candidates = [candidate_paths(graph, f) for f in flows]

    linear: dict[str, float] = {}
    quadratic: dict[tuple[str, str], float] = {}
    names: list[str] = []

    for f in flows:
        for k in range(config.K_ROUTES):
            n = var_name(f.index, k)
            names.append(n)
            linear[n] = path_time(graph, candidates[f.index][k])

    for i, f_i in enumerate(flows):
        for j in range(i + 1, len(flows)):
            f_j = flows[j]
            w = pair_weight(f_i, f_j)
            for k in range(config.K_ROUTES):
                for kp in range(config.K_ROUTES):
                    p = shared_penalty(graph, candidates[i][k], candidates[j][kp], w)
                    if p > 0:
                        quadratic[(var_name(i, k), var_name(j, kp))] = p

    # Recorte + reescalado: ACCIDENT (+5000) no debe aplastar la restricción one-hot (penalty=100)
    clipped_lin = {n: min(c, config.COEF_CLIP) for n, c in linear.items()}
    clipped_quad = {k: min(c, config.COEF_CLIP) for k, c in quadratic.items()}
    max_coef = max([*clipped_lin.values(), *clipped_quad.values(), 1.0])
    scale = min(1.0, config.COEF_TARGET / max_coef)

    qp = QuadraticProgram("superpose_routing")
    for n in names:
        qp.binary_var(n)
    qp.minimize(
        linear={n: c * scale for n, c in clipped_lin.items()},
        quadratic={k: c * scale for k, c in clipped_quad.items()},
    )
    for f in flows:
        qp.linear_constraint(
            linear={var_name(f.index, k): 1 for k in range(config.K_ROUTES)},
            sense="==", rhs=1, name=f"one_hot_{f.index}",
        )
    return QuboModel(program=qp, flows=flows, candidates=candidates, var_names=names, scale=scale)
