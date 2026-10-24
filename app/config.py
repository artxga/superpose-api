"""Constantes de configuración de Superpose."""

# --- Modelo QUBO -----------------------------------------------------------
K_ROUTES = 2                 # rutas candidatas por flujo
N_FLOWS = 3                  # usuario + 2 flujos de fondo  -> 6 qubits
QUBO_PENALTY = 100.0         # penalización one-hot (QuadraticProgramToQubo)
COEF_CLIP = 200.0            # tope de coeficientes (evita que ACCIDENT aplaste el QUBO)
COEF_TARGET = 50.0           # coeficiente máximo tras reescalado (< QUBO_PENALTY)
VEHICLES_REF = 20.0          # normaliza el peso de congestión w_ij = (v_i + v_j) / ref

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

# --- Topología (mapa basado en Lima) ------------------------------------------
# Nodo: id -> (distrito, latitud, longitud). Los IDs de la API no cambian.
NODE_INFO = {
    "NODO_A": ("Callao", -12.057, -77.118),
    "NODO_B": ("Los Olivos", -11.990, -77.070),
    "NODO_C": ("Cercado de Lima", -12.046, -77.043),
    "NODO_D": ("San Isidro", -12.098, -77.037),
    "NODO_E": ("San Juan de Lurigancho", -12.003, -77.008),
    "NODO_F": ("La Molina", -12.083, -76.942),
}
NODES = list(NODE_INFO)

# Arista: (u, v, velocidad_kmh, carriles, length_km_override | None)
# Si no hay override, length_km = haversine(u, v) * SINUOSITY.
EDGES = [
    ("NODO_A", "NODO_C", 50.0, 3, None),   # vía central rápida
    ("NODO_C", "NODO_D", 50.0, 3, None),   # central
    ("NODO_D", "NODO_F", 50.0, 3, None),   # central
    ("NODO_A", "NODO_B", 35.0, 2, None),   # periférica norte
    ("NODO_B", "NODO_D", 30.0, 2, None),   # cruce
    ("NODO_B", "NODO_E", 35.0, 2, None),   # periférica norte
    ("NODO_E", "NODO_F", 35.0, 2, None),   # periférica
    ("NODO_C", "NODO_E", 30.0, 1, None),   # periférica sur
]

# --- Parámetros derivados de la geometría ---------------------------------------
SINUOSITY = 1.3              # factor de curvatura vial sobre la distancia en línea recta
PENALTY_PER_KM = 2.0         # base_penalty = length_km * PENALTY_PER_KM
CAPACITY_PER_LANE = 15       # vehículos simultáneos admitidos por carril (escala de demo)
# base_time (min) = length_km / speed_kmh * 60
