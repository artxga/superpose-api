"""Solver híbrido: QAOA (Aer Sampler) con fallback exacto NumPy."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from qiskit.primitives.containers.sampler_pub import SamplerPub
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import SamplerV2  # V1 `Sampler` ya no es compatible con Qiskit 2.x / qiskit-algorithms 0.4
from qiskit_algorithms import NumPyMinimumEigensolver, QAOA
from qiskit_algorithms.optimizers import COBYLA
from qiskit_optimization import QuadraticProgram
from qiskit_optimization.algorithms import MinimumEigenOptimizer, OptimizationResultStatus
from qiskit_optimization.converters import QuadraticProgramToQubo

from . import config

log = logging.getLogger("superpose.solver")


@dataclass
class SolveOutcome:
    x: list[int]
    fval: float
    solver_used: str
    feasible: bool
    top_probabilities: list[dict] = field(default_factory=list)
    execution_time_ms: float = 0.0
    note: str | None = None

    @property
    def bitstring(self) -> str:
        return "".join(str(int(v)) for v in self.x)


def _optimizer(min_eigen_solver) -> MinimumEigenOptimizer:
    return MinimumEigenOptimizer(
        min_eigen_solver,
        converters=QuadraticProgramToQubo(penalty=config.QUBO_PENALTY),
    )


class Sampler(SamplerV2):
    """`qiskit_aer.primitives.SamplerV2` + transpilación a la base de AerSimulator.

    SamplerV2 no transpila; QAOA entrega circuitos con instrucciones compuestas
    (p. ej. `QAOA`) que Aer no reconoce directamente.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pm = generate_preset_pass_manager(optimization_level=0, backend=AerSimulator())

    def run(self, pubs, *, shots=None):
        prepared = []
        for pub in pubs:
            pub = SamplerPub.coerce(pub, shots)
            prepared.append(SamplerPub(self._pm.run(pub.circuit), parameter_values=pub.parameter_values,
                                       shots=pub.shots, validate=False))
        return super().run(prepared, shots=shots)


def _qaoa() -> QAOA:
    sampler = Sampler(default_shots=config.SAMPLER_SHOTS, seed=config.SAMPLER_SEED)
    return QAOA(sampler=sampler, optimizer=COBYLA(maxiter=config.COBYLA_MAXITER), reps=config.QAOA_REPS)


def _top(result) -> list[dict]:
    samples = sorted(result.samples, key=lambda s: s.probability, reverse=True)[: config.TOP_PROBABILITIES]
    return [
        {
            "bitstring": "".join(str(int(v)) for v in s.x),
            "probability": round(float(s.probability), 5),
            "fval": round(float(s.fval), 4),
            "feasible": s.status == OptimizationResultStatus.SUCCESS,
        }
        for s in samples
    ]


def _best_feasible(result):
    feasible = [s for s in result.samples if s.status == OptimizationResultStatus.SUCCESS]
    if not feasible:
        return None
    return min(feasible, key=lambda s: (s.fval, -s.probability))


def _to_outcome(result, solver: str, note: str | None = None) -> SolveOutcome | None:
    if result.status == OptimizationResultStatus.SUCCESS:
        return SolveOutcome([int(v) for v in result.x], float(result.fval), solver, True, _top(result), note=note)
    best = _best_feasible(result)
    if best is None:
        return None
    return SolveOutcome([int(v) for v in best.x], float(best.fval), solver, True, _top(result),
                        note=(note or "") + " Mejor muestra factible del QAOA (la solución principal violaba one-hot).")


def solve(program: QuadraticProgram) -> SolveOutcome:
    start = time.perf_counter()
    outcome: SolveOutcome | None = None
    note: str | None = None
    try:
        outcome = _to_outcome(_optimizer(_qaoa()).solve(program), "QAOA")
        if outcome is None:
            note = "QAOA no produjo muestras factibles; se usó NumPyMinimumEigensolver."
    except Exception as exc:  # noqa: BLE001 - cualquier fallo cuántico activa el fallback
        log.warning("QAOA falló (%s); usando fallback clásico", exc)
        note = f"QAOA falló ({type(exc).__name__}); se usó NumPyMinimumEigensolver."

    if outcome is None:
        result = _optimizer(NumPyMinimumEigensolver()).solve(program)
        outcome = _to_outcome(result, "NumPyMinimumEigensolver (fallback)", note)
        if outcome is None:  # no debería ocurrir: el problema siempre tiene solución factible
            outcome = SolveOutcome([int(v) for v in result.x], float(result.fval),
                                   "NumPyMinimumEigensolver (fallback)", False, note=note)

    outcome.execution_time_ms = round((time.perf_counter() - start) * 1000, 2)
    return outcome
