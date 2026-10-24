"""Grafo de tráfico en memoria (networkx) con eventos dinámicos en aristas."""
from __future__ import annotations

import threading

import networkx as nx

from . import config

EdgeKey = tuple[str, str]


class SuperposeError(Exception):
    """Error de dominio mapeado a una respuesta HTTP."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# Alias de retrocompatibilidad
QNavError = SuperposeError


def edge_key(u: str, v: str) -> EdgeKey:
    return (u, v) if u <= v else (v, u)


def path_edges(path: list[str]) -> list[EdgeKey]:
    return [edge_key(a, b) for a, b in zip(path, path[1:])]


class GraphState:
    """Estado mutable del grafo; seguro entre hilos."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._graph = nx.Graph()
        self._loads: dict[EdgeKey, float] = {}
        self.background_flows: list[dict] | None = None
        self._build()

    def _build(self) -> None:
        g = nx.Graph()
        g.add_nodes_from(config.NODES)
        for u, v, t, p, cap in config.EDGES:
            g.add_edge(
                u, v,
                base_time=t, base_penalty=p, capacity=cap,
                time=t, penalty=p, event="NORMAL",
            )
        self._graph = g
        self._loads = {edge_key(u, v): 0.0 for u, v in g.edges}

    # ------------------------------------------------------------------ eventos
    def apply_event(self, source: str, target: str, event_type: str) -> None:
        with self._lock:
            if not self._graph.has_edge(source, target):
                raise QNavError(404, f"La arista {source} - {target} no existe")
            data = self._graph[source][target]
            t_mul, t_add, p_mul = config.EVENT_MODIFIERS[event_type]
            data["time"] = data["base_time"] * t_mul + t_add
            data["penalty"] = data["base_penalty"] * p_mul
            data["event"] = event_type

    def reset(self) -> None:
        with self._lock:
            for u, v in self._graph.edges:
                self.apply_event(u, v, "NORMAL")
            self._loads = {edge_key(u, v): 0.0 for u, v in self._graph.edges}

    # ------------------------------------------------------------------ lecturas
    def snapshot(self) -> nx.Graph:
        """Copia aislada del grafo para calcular sin bloquear escrituras."""
        with self._lock:
            return self._graph.copy()

    def set_loads(self, loads: dict[EdgeKey, float]) -> None:
        with self._lock:
            self._loads = {k: float(loads.get(k, 0.0)) for k in self._loads}

    def topology(self) -> dict:
        with self._lock:
            edges = []
            events = []
            for u, v, d in self._graph.edges(data=True):
                key = edge_key(u, v)
                load = self._loads.get(key, 0.0)
                edges.append({
                    "source": key[0], "target": key[1],
                    "base_time": d["base_time"],
                    "current_time": d["time"],
                    "current_penalty": d["penalty"],
                    "capacity": d["capacity"],
                    "load": load,
                    "saturation": round(load / d["capacity"], 4),
                    "event": d["event"],
                })
                if d["event"] != "NORMAL":
                    events.append({"source": key[0], "target": key[1], "event_type": d["event"]})
            return {"nodes": list(self._graph.nodes), "edges": edges, "active_events": events}

    def set_background_flows(self, flows: list[dict] | None) -> None:
        with self._lock:
            self.background_flows = flows


state = GraphState()
