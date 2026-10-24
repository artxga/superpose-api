"""Modelos Pydantic v2 de la API."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class EventType(str, Enum):
    NORMAL = "NORMAL"
    TRAFFIC_JAM = "TRAFFIC_JAM"
    ROADWORK = "ROADWORK"
    ACCIDENT = "ACCIDENT"


class FlowSpec(BaseModel):
    origin: str = Field(examples=["NODO_B"])
    destination: str = Field(examples=["NODO_F"])
    vehicles: int = Field(default=20, ge=1, le=1000, description="Vehículos del flujo")

    @model_validator(mode="after")
    def _distinct(self):
        if self.origin == self.destination:
            raise ValueError("origin y destination deben ser distintos")
        return self


class OptimizeRequest(BaseModel):
    origin: str = Field(examples=["NODO_A"])
    destination: str = Field(examples=["NODO_F"])
    vehicles: int = Field(default=1, ge=1, le=1000)
    background_flows: list[FlowSpec] | None = Field(
        default=None, min_length=2, max_length=2,
        description="Exactamente 2 flujos de fondo (mantiene 6 qubits). Opcional.",
    )

    @model_validator(mode="after")
    def _distinct(self):
        if self.origin == self.destination:
            raise ValueError("origin y destination deben ser distintos")
        return self


class BackgroundFlowsRequest(BaseModel):
    background_flows: list[FlowSpec] = Field(min_length=2, max_length=2)


class EventReport(BaseModel):
    source: str = Field(examples=["NODO_B"])
    target: str = Field(examples=["NODO_D"])
    event_type: EventType


class RouteMetrics(BaseModel):
    route: list[str]
    travel_time: float
    congestion_penalty: float
    estimated_time: float


class FlowAssignment(BaseModel):
    name: str
    origin: str
    destination: str
    vehicles: int
    qaoa_route: list[str]
    selfish_route: list[str]


class EdgeLoad(BaseModel):
    source: str
    target: str
    capacity: int
    event: str
    vehicles_optimized: int
    saturation_optimized: float
    vehicles_selfish: int
    saturation_selfish: float


class Comparison(BaseModel):
    user_time_saved: float
    user_improvement_pct: float
    system_cost_optimized: float
    system_cost_selfish: float
    system_improvement_pct: float


class QuantumTelemetry(BaseModel):
    qubits_used: int
    optimal_bitstring: str
    variables: list[str]
    top_probabilities: list[dict]
    execution_time_ms: float
    solver_used: str
    feasible: bool
    qubo_scale: float
    note: str | None = None


class OptimizeResponse(BaseModel):
    origin: str
    destination: str
    optimized: RouteMetrics
    selfish: RouteMetrics
    comparison: Comparison
    flows: list[FlowAssignment]
    edge_loads: list[EdgeLoad]
    quantum_telemetry: QuantumTelemetry
    total_time_ms: float
