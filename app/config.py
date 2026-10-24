"""Constantes de configuración de Superpose."""

# --- Modelo QUBO -----------------------------------------------------------
K_ROUTES = 2                 # rutas candidatas por flujo
N_FLOWS = 3                  # usuario + 2 flujos de fondo  -> 6 qubits
QUBO_PENALTY = 100.0         # penalización one-hot (QuadraticProgramToQubo)
COEF_CLIP = 200.0            # tope de coeficientes (evita que ACCIDENT aplaste el QUBO)
COEF_TARGET = 50.0           # coeficiente máximo tras reescalado (< QUBO_PENALTY)
VEHICLES_REF = 50.0          # normaliza el peso de congestión w_ij = (v_i + v_j) / ref

# --- Solver QAOA -----------------------------------------------------------
QAOA_REPS = 2
COBYLA_MAXITER = 40
SAMPLER_SHOTS = 1024
SAMPLER_SEED = 42
TOP_PROBABILITIES = 5

# --- Flujos por defecto (si el request no los define) -----------------------
DEFAULT_USER_VEHICLES = 1
DEFAULT_BACKGROUND_FLOWS = [
    {"origin": "NODO_B", "destination": "NODO_F", "vehicles": 20},
    {"origin": "NODO_A", "destination": "NODO_E", "vehicles": 30},
]

# --- Eventos: (multiplicador de tiempo, suma de tiempo, multiplicador de penalización)
EVENT_MODIFIERS = {
    "NORMAL": (1.0, 0.0, 1.0),
    "TRAFFIC_JAM": (1.8, 0.0, 4.0),
    "ROADWORK": (1.5, 0.0, 6.0),
    "ACCIDENT": (1.0, 5000.0, 1.0),
}

# --- Topología: (u, v, base_time, base_penalty, capacity_vehicles) ------------
EDGES = [
    ("NODO_A", "NODO_C", 7.0, 12.0, 40),   # vía central rápida
    ("NODO_C", "NODO_D", 5.0, 15.0, 35),   # central
    ("NODO_D", "NODO_F", 6.0, 15.0, 40),   # central
    ("NODO_A", "NODO_B", 12.0, 6.0, 50),   # periférica norte
    ("NODO_B", "NODO_D", 8.0, 8.0, 40),    # cruce
    ("NODO_B", "NODO_E", 10.0, 6.0, 45),   # periférica norte
    ("NODO_E", "NODO_F", 11.0, 6.0, 45),   # periférica
    ("NODO_C", "NODO_E", 14.0, 6.0, 45),   # periférica sur
]
NODES = ["NODO_A", "NODO_B", "NODO_C", "NODO_D", "NODO_E", "NODO_F"]
