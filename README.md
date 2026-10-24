# Superpose – API REST Híbrida Clásica-Cuántica (QAOA)

**Superpose** es un motor de enrutamiento dinámico y optimización de tráfico urbano desarrollado para la hackathon de IBM Quantum. Combina la teoría de grafos clásica (`networkx`) con computación cuántica variacional (**QAOA** vía `qiskit`, `qiskit-aer` y `qiskit-optimization`) para resolver el problema de congestión vehicular cruzada reduciendo la latencia a menos de **250 ms**.

---

## 🚀 Inicio Rápido

### Requisitos Previos
- Python 3.11, 3.12 o 3.13
- Entorno virtual recomendado

### Instalación y Ejecución
```bash
# 1. Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Iniciar el servidor API
uvicorn app.main:app --reload --port 8000
```

- **Swagger UI interactivo:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc alternativo:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Colección Postman:** Archivo listo para importar en [superpose_postman_collection.json](file:///Volumes/HIKSEMI%20Media/Repos/Projects/ibm-quantum/superpose_postman_collection.json)

### Ejecución de Pruebas Automatizadas
```bash
pytest -v
```

---

## 🧠 Arquitectura Cuántica y Modelo QUBO

### Mapeo de 6 Qubits (Variables Binarias)
En lugar de asignar qubits ineficientemente por arista ($|E| \gg 6$), Superpose extrae las $K=2$ rutas candidatas más cortas (`networkx.shortest_simple_paths`) para $N=3$ flujos de tráfico concurrentes (1 usuario + 2 flujos de fondo):
$$\text{Total variables} = 3 \text{ flujos} \times 2 \text{ rutas} = 6 \text{ qubits } (x_{0,0}, x_{0,1}, x_{1,0}, x_{1,1}, x_{2,0}, x_{2,1})$$

| Qubit | Variable | Flujo | Significado |
|---|---|---|---|
| **q0** | `x_0_0` | Usuario principal | `1` si toma la Ruta 1 (más rápida individualmente) |
| **q1** | `x_0_1` | Usuario principal | `1` si toma la Ruta 2 (vía alternativa) |
| **q2** | `x_1_0` | Flujo de Fondo 1 | `1` si Fondo 1 toma su Ruta 1 |
| **q3** | `x_1_1` | Flujo de Fondo 1 | `1` si Fondo 1 toma su Ruta 2 |
| **q4** | `x_2_0` | Flujo de Fondo 2 | `1` si Fondo 2 toma su Ruta 1 |
| **q5** | `x_2_1` | Flujo de Fondo 2 | `1` si Fondo 2 toma su Ruta 2 |

### Función de Costo Cuadrática
1. **Término Lineal ($C_{i,k}$):** Suma del tiempo base de viaje de las aristas en la ruta candidata $k$ del flujo $i$.
2. **Término Cuadrático ($P_e$):** Si dos flujos $i \neq j$ comparten una arista $e$, se penaliza la congestión con un factor acoplado $P_e \cdot w_{ij} \cdot x_{i,k} \cdot x_{j,k'}$, donde $w_{ij} = (v_i + v_j) / 20$ refleja el volumen conjunto de vehículos.
3. **Restricción One-Hot:** Cada flujo debe seleccionar exactamente una ruta:
   $$\sum_{k=0}^{1} x_{i,k} = 1 \quad \forall i \in \{0, 1, 2\}$$
   Convertida a QUBO mediante `QuadraticProgramToQubo(penalty=100.0)`.

### Eventos Dinámicos y Resiliencia
- `NORMAL`: `tiempo = base_time`, `penalización = base_penalty`
- `TRAFFIC_JAM`: `tiempo = base_time * 1.8`, `penalización = base_penalty * 4.0`
- `ROADWORK`: `tiempo = base_time * 1.5`, `penalización = base_penalty * 6.0`
- `ACCIDENT`: `tiempo = base_time + 5000.0` (fuerza matemáticamente al circuito QAOA a desestimar rutas afectadas).

### Mapa de Lima y Parámetros Geográficos
Los nodos representan distritos de Lima (los IDs de la API no cambian) y cada arista se parametriza con longitud, velocidad y carriles:

| Nodo | Distrito | Lat, Lon |
|---|---|---|
| `NODO_A` | Callao | -12.057, -77.118 |
| `NODO_B` | Los Olivos | -11.990, -77.070 |
| `NODO_C` | Cercado de Lima | -12.046, -77.043 |
| `NODO_D` | San Isidro | -12.098, -77.037 |
| `NODO_E` | San Juan de Lurigancho | -12.003, -77.008 |
| `NODO_F` | La Molina | -12.083, -76.942 |

- `length_km = haversine(u, v) × 1.3` (factor de sinuosidad vial; las coordenadas son aproximadas).
- `base_time (min) = length_km / speed_kmh × 60` (tiempo en flujo libre).
- `base_penalty = length_km × 2.0` y `capacity = lanes × 15` vehículos (escala de demo).
- Los eventos modifican `base_time` y `base_penalty` como se indica arriba; la congestión entre flujos la resuelve QAOA.

---

## 📡 Documentación de Endpoints y Contratos

### 1. `GET /api/v1/topology`
Obtiene el estado actual del grafo de tráfico en memoria: nodos, aristas, tiempos actuales, nivel de saturación vehicular y eventos activos.

- **Método:** `GET`
- **URL:** `/api/v1/topology`
- **Headers:** Ninguno requerido.

#### Contrato de Respuesta (200 OK)
```json
{
  "nodes": ["NODO_A", "NODO_B", "NODO_C", "NODO_D", "NODO_E", "NODO_F"],
  "node_details": [
    {"id": "NODO_A", "label": "Callao", "lat": -12.057, "lon": -77.118}
  ],
  "edges": [
    {
      "source": "NODO_A",
      "target": "NODO_C",
      "length_km": 10.72,
      "speed_kmh": 50.0,
      "lanes": 3,
      "base_time": 12.86,
      "current_time": 12.86,
      "current_penalty": 21.44,
      "capacity": 45,
      "load": 1.0,
      "saturation": 0.0222,
      "event": "NORMAL"
    }
  ],
  "active_events": [
    {
      "source": "NODO_B",
      "target": "NODO_D",
      "event_type": "TRAFFIC_JAM"
    }
  ]
}
```

#### Descripción de Campos
- `nodes` *(list[string])*: Identificadores de los 6 nodos de la red.
- `node_details[]` *(object)*: `id`, `label` (distrito de Lima), `lat`, `lon`.
- `edges[].length_km` *(float)*: Longitud vial estimada de la arista.
- `edges[].speed_kmh` *(float)*: Velocidad en flujo libre.
- `edges[].lanes` *(integer)*: Número de carriles.
- `edges[].base_time` *(float)*: Tiempo en minutos en flujo libre (`length_km / speed_kmh × 60`).
- `edges[].current_time` *(float)*: Tiempo actual modificado por incidentes viales.
- `edges[].capacity` *(integer)*: Capacidad vehicular (`lanes × 15`) antes de saturación.
- `edges[].load` *(float)*: Carga actual de vehículos en tránsito según la última optimización.
- `edges[].saturation` *(float)*: Razón `load / capacity` ($0.0$ a $\ge 1.0$).
- `edges[].event` *(string)*: `NORMAL` | `TRAFFIC_JAM` | `ROADWORK` | `ACCIDENT`.
- `active_events` *(list[object])*: Lista de aristas con eventos distintos de `NORMAL`.

#### Ejemplo cURL
```bash
curl -X GET "http://localhost:8000/api/v1/topology"
```

---

### 2. `POST /api/v1/route/optimize`
Ejecuta la optimización híbrida cuántica QAOA comparándola con el enrutamiento clásico egoísta (Dijkstra).

- **Método:** `POST`
- **URL:** `/api/v1/route/optimize`
- **Headers:** `Content-Type: application/json`

#### Contrato de Solicitud (Request Body)
```json
{
  "origin": "NODO_A",
  "destination": "NODO_F",
  "vehicles": 1,
  "background_flows": [
    {
      "origin": "NODO_B",
      "destination": "NODO_F",
      "vehicles": 20
    },
    {
      "origin": "NODO_A",
      "destination": "NODO_E",
      "vehicles": 30
    }
  ]
}
```

#### Descripción de Campos de Entrada
- `origin` *(string, requerido)*: Nodo de inicio (`NODO_A` a `NODO_F`).
- `destination` *(string, requerido)*: Nodo de destino (distinto del origen).
- `vehicles` *(integer, opcional, default: 1)*: Número de vehículos del usuario.
- `background_flows` *(list[FlowSpec], opcional)*: Exactamente 2 flujos de fondo con los que compite el usuario. Si se omite, se usan los flujos predeterminados (`B→F` con 20 vehículos y `A→E` con 30 vehículos).

#### Contrato de Respuesta (200 OK)
```json
{
  "origin": "NODO_A",
  "destination": "NODO_F",
  "optimized": {
    "route": [
      "NODO_A",
      "NODO_C",
      "NODO_E",
      "NODO_F"
    ],
    "travel_time": 54.21,
    "congestion_penalty": 0.0,
    "estimated_time": 54.21
  },
  "selfish": {
    "route": [
      "NODO_A",
      "NODO_C",
      "NODO_D",
      "NODO_F"
    ],
    "travel_time": 38.25,
    "congestion_penalty": 33.232,
    "estimated_time": 71.482
  },
  "comparison": {
    "user_time_saved": 17.272,
    "user_improvement_pct": 24.16,
    "system_cost_optimized": 138.77,
    "system_cost_selfish": 174.304,
    "system_improvement_pct": 20.39
  },
  "flows": [
    {
      "name": "usuario",
      "origin": "NODO_A",
      "destination": "NODO_F",
      "vehicles": 1,
      "qaoa_route": [
        "NODO_A",
        "NODO_C",
        "NODO_E",
        "NODO_F"
      ],
      "selfish_route": [
        "NODO_A",
        "NODO_C",
        "NODO_D",
        "NODO_F"
      ]
    },
    {
      "name": "fondo_1",
      "origin": "NODO_B",
      "destination": "NODO_F",
      "vehicles": 20,
      "qaoa_route": [
        "NODO_B",
        "NODO_D",
        "NODO_F"
      ],
      "selfish_route": [
        "NODO_B",
        "NODO_E",
        "NODO_F"
      ]
    },
    {
      "name": "fondo_2",
      "origin": "NODO_A",
      "destination": "NODO_E",
      "vehicles": 30,
      "qaoa_route": [
        "NODO_A",
        "NODO_B",
        "NODO_E"
      ],
      "selfish_route": [
        "NODO_A",
        "NODO_C",
        "NODO_E"
      ]
    }
  ],
  "edge_loads": [
    {
      "source": "NODO_A",
      "target": "NODO_C",
      "capacity": 45,
      "event": "NORMAL",
      "vehicles_optimized": 1,
      "saturation_optimized": 0.0222,
      "vehicles_selfish": 31,
      "saturation_selfish": 0.6889
    },
    {
      "source": "NODO_A",
      "target": "NODO_B",
      "capacity": 30,
      "event": "NORMAL",
      "vehicles_optimized": 30,
      "saturation_optimized": 1.0,
      "vehicles_selfish": 0,
      "saturation_selfish": 0.0
    }
  ],
  "quantum_telemetry": {
    "qubits_used": 6,
    "optimal_bitstring": "010101",
    "variables": [
      "x_0_0",
      "x_0_1",
      "x_1_0",
      "x_1_1",
      "x_2_0",
      "x_2_1"
    ],
    "top_probabilities": [
      {
        "bitstring": "000010",
        "probability": 0.01869,
        "fval": 24.8418,
        "feasible": false
      }
    ],
    "execution_time_ms": 184.22,
    "solver_used": "QAOA",
    "feasible": true,
    "qubo_scale": 0.86436,
    "note": null
  },
  "total_time_ms": 185.38
}
```

#### Interpretación de Resultados y Comparativa
- **Ruta Egoísta (Dijkstra):** Cada conductor toma la ruta de menor tiempo individual sin coordinarse. En el ejemplo, el usuario y el `fondo_2` pasan por `NODO_A → NODO_C` (31 vehículos, 69% de saturación) y el usuario sigue por la vía central `C → D → F`, donde coincide con otros flujos y acumula congestión.
- **Ruta Optimizada (QAOA):** El algoritmo cuántico desacopla las trayectorias: el `fondo_2` se desvía por la periférica `A → B → E` y el `fondo_1` por `B → D → F`, y el usuario toma `A → C → E → F`, más larga pero sin congestión. Aunque su tiempo de viaje base es mayor, el **tiempo estimado baja un 24.16%** (de 71.48 a 54.21 min) y el costo global del sistema baja un **20.39%**.
- **Telemetría Cuántica:**
  - `optimal_bitstring`: `010101` descompuesto en pares `[01][01][01]` indica que los tres flujos tomaron su Ruta 2 (la candidata alternativa).
  - `execution_time_ms`: Tiempo de ejecución del algoritmo cuántico en simulador (~170 ms). El resultado es reproducible (semilla y punto inicial fijos).
  - `solver_used`: Identifica si la solución provino del circuito variacional `QAOA` o del fallback exacto `NumPyMinimumEigensolver`.

#### Ejemplo cURL
```bash
curl -X POST "http://localhost:8000/api/v1/route/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "NODO_A",
    "destination": "NODO_F",
    "vehicles": 1
  }'
```

---

### 3. `POST /api/v1/events/report`
Reporta un evento dinámico en una arista específica (ej. accidente o atasco). Actualiza inmediatamente los pesos de tiempo y penalización del grafo en memoria.

- **Método:** `POST`
- **URL:** `/api/v1/events/report`
- **Headers:** `Content-Type: application/json`

#### Contrato de Solicitud (Request Body)
```json
{
  "source": "NODO_B",
  "target": "NODO_D",
  "event_type": "TRAFFIC_JAM"
}
```

#### Tipos de Eventos Permitidos (`event_type`)
| Evento | Multiplicador de Tiempo | Suma Fija de Tiempo | Multiplicador Penalización |
|---|---|---|---|
| `NORMAL` | $1.0\times$ | $+0.0$ min | $1.0\times$ |
| `TRAFFIC_JAM` | $1.8\times$ | $+0.0$ min | $4.0\times$ |
| `ROADWORK` | $1.5\times$ | $+0.0$ min | $6.0\times$ |
| `ACCIDENT` | $1.0\times$ | $+5000.0$ min | $1.0\times$ |

#### Contrato de Respuesta (200 OK)
Retorna el estado completo y actualizado de la topología del grafo (idéntico al esquema de `GET /api/v1/topology`), reflejando el cambio de peso en la arista afectada y agregándola a `active_events`.

#### Ejemplo cURL
```bash
curl -X POST "http://localhost:8000/api/v1/events/report" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "NODO_C",
    "target": "NODO_D",
    "event_type": "ACCIDENT"
  }'
```

---

### 4. `POST /api/v1/events/reset`
Restaura todas las aristas de la red al estado inicial `NORMAL` y restablece los contadores de carga vehicular.

- **Método:** `POST`
- **URL:** `/api/v1/events/reset`
- **Headers:** Ninguno requerido.
- **Request Body:** Vacío.

#### Contrato de Respuesta (200 OK)
Retorna la topología limpia donde `active_events` es una lista vacía `[]` y todas las aristas tienen sus valores `base_time` y `base_penalty`.

#### Ejemplo cURL
```bash
curl -X POST "http://localhost:8000/api/v1/events/reset"
```

---

### 5. `PUT /api/v1/flows/background`
Permite fijar dinámicamente en memoria los dos flujos de tráfico de fondo concurrentes para que apliquen a todas las optimizaciones subsiguientes sin tener que enviarlos en cada petición.

- **Método:** `PUT`
- **URL:** `/api/v1/flows/background`
- **Headers:** `Content-Type: application/json`

#### Contrato de Solicitud (Request Body)
```json
{
  "background_flows": [
    {
      "origin": "NODO_C",
      "destination": "NODO_F",
      "vehicles": 40
    },
    {
      "origin": "NODO_B",
      "destination": "NODO_E",
      "vehicles": 15
    }
  ]
}
```

#### Contrato de Respuesta (200 OK)
```json
{
  "background_flows": [
    {
      "origin": "NODO_C",
      "destination": "NODO_F",
      "vehicles": 40
    },
    {
      "origin": "NODO_B",
      "destination": "NODO_E",
      "vehicles": 15
    }
  ]
}
```

#### Ejemplo cURL
```bash
curl -X PUT "http://localhost:8000/api/v1/flows/background" \
  -H "Content-Type: application/json" \
  -d '{
    "background_flows": [
      {"origin": "NODO_C", "destination": "NODO_F", "vehicles": 40},
      {"origin": "NODO_B", "destination": "NODO_E", "vehicles": 15}
    ]
  }'
```

---

## 🛑 Manejo de Errores y Códigos HTTP

La API implementa validación estricta con Pydantic v2 y respuestas JSON consistentes:

| Código | Significado | Causa Típica |
|---|---|---|
| `200 OK` | Operación exitosa | Petición procesada correctamente. |
| `404 Not Found` | Recurso no encontrado | Arista o nodo inexistente en la red (`detail: "La arista NODO_A - NODO_F no existe"`). |
| `422 Unprocessable Entity` | Error de validación de datos | `origin` y `destination` iguales, número de flujos distinto a 2, o `event_type` inválido. |
| `500 Internal Server Error` | Error de ejecución | Fallo no recuperable (el backend cuenta con fallback automático de QAOA a NumPy para evitar fallos 500). |

Ejemplo de error 422:
```json
{
  "detail": [
    {
      "loc": ["body", "origin"],
      "msg": "origin y destination deben ser distintos",
      "type": "value_error"
    }
  ]
}
```
