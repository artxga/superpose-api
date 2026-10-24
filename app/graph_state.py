"""Grafo de tráfico en memoria (networkx) con eventos dinámicos en aristas."""
from __future__ import annotations

import math
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


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta (km) entre dos coordenadas."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


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
        for node, (label, lat, lon) in config.NODE_INFO.items():
            g.add_node(node, label=label, lat=lat, lon=lon)
        for u, v, speed, lanes, length_override in config.EDGES:
            length = length_override if length_override is not None else (
                haversine_km(g.nodes[u]["lat"], g.nodes[u]["lon"], g.nodes[v]["lat"], g.nodes[v]["lon"])
                * config.SINUOSITY
            )
            length = round(length, 2)
            t = round(length / speed * 60.0, 2)            # minutos en flujo libre
            p = round(length * config.PENALTY_PER_KM, 2)
            g.add_edge(
                u, v,
                length_km=length, speed_kmh=speed, lanes=lanes,
                base_time=t, base_penalty=p, capacity=lanes * config.CAPACITY_PER_LANE,
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
                    "length_km": d["length_km"],
                    "speed_kmh": d["speed_kmh"],
                    "lanes": d["lanes"],
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
            node_details = [
                {"id": n, "label": d["label"], "lat": d["lat"], "lon": d["lon"]}
                for n, d in self._graph.nodes(data=True)
            ]
            return {"nodes": list(self._graph.nodes), "node_details": node_details,
                    "edges": edges, "active_events": events}

    def set_background_flows(self, flows: list[dict] | None) -> None:
        with self._lock:
            self.background_flows = flows


state = GraphState()
