"""Aplicación FastAPI de Superpose."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import routing
from .graph_state import SuperposeError, state
from .qubo_builder import Flow, build_qubo
from .schemas import BackgroundFlowsRequest, EventReport, OptimizeRequest, OptimizeResponse
from .solver import solve


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Calentamiento: la primera ejecución de Qiskit es la más lenta
    g = state.snapshot()
    flows = [Flow(0, "w", "NODO_A", "NODO_F", 1), Flow(1, "w", "NODO_B", "NODO_F", 1),
             Flow(2, "w", "NODO_A", "NODO_E", 1)]
    solve(build_qubo(g, flows).program)
    yield


app = FastAPI(
    title="Superpose API",
    description="Motor híbrido clásico-cuántico de optimización y enrutamiento dinámico de tráfico con QAOA (Qiskit).",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(SuperposeError)
async def superpose_error_handler(_: Request, exc: SuperposeError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/", include_in_schema=False)
def root():
    return {"service": "Superpose", "docs": "/docs"}


@app.get("/api/v1/topology", tags=["topology"])
def get_topology():
    return state.topology()


@app.post("/api/v1/route/optimize", response_model=OptimizeResponse, tags=["routing"])
def optimize_route(req: OptimizeRequest):
    return routing.optimize(req, state)


@app.put("/api/v1/flows/background", tags=["routing"])
def set_background_flows(req: BackgroundFlowsRequest):
    flows = [f.model_dump() for f in req.background_flows]
    for f in flows:
        for n in (f["origin"], f["destination"]):
            if n not in state.snapshot():
                raise QNavError(404, f"Nodo desconocido: {n}")
    state.set_background_flows(flows)
    return {"background_flows": flows}


@app.post("/api/v1/events/report", tags=["events"])
def report_event(req: EventReport):
    state.apply_event(req.source, req.target, req.event_type.value)
    return state.topology()


@app.post("/api/v1/events/reset", tags=["events"])
def reset_events():
    state.reset()
    return state.topology()
