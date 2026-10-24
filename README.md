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
2. **Término Cuadrático ($P_e$):** Si dos flujos $i \neq j$ comparten una arista $e$, se penaliza la congestión con un factor acoplado $P_e \cdot w_{ij} \cdot x_{i,k} \cdot x_{j,k'}$, donde $w_{ij} = (v_i + v_j) / 50$ refleja el volumen conjunto de vehículos.
3. **Restricción One-Hot:** Cada flujo debe seleccionar exactamente una ruta:
   $$\sum_{k=0}^{1} x_{i,k} = 1 \quad \forall i \in \{0, 1, 2\}$$
   Convertida a QUBO mediante `QuadraticProgramToQubo(penalty=100.0)`.

### Eventos Dinámicos y Resiliencia
- `NORMAL`: `tiempo = base_time`, `penalización = base_penalty`
- `TRAFFIC_JAM`: `tiempo = base_time * 1.8`, `penalización = base_penalty * 4.0`
- `ROADWORK`: `tiempo = base_time * 1.5`, `penalización = base_penalty * 6.0`
- `ACCIDENT`: `tiempo = base_time + 5000.0` (fuerza matemáticamente al circuito QAOA a desestimar rutas afectadas).

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
  "edges": [
    {
      "source": "NODO_A",
      "target": "NODO_C",
      "base_time": 7.0,
      "current_time": 7.0,
      "current_penalty": 12.0,
      "capacity": 40,
      "load": 1.0,
      "saturation": 0.025,
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
- `edges[].base_time` *(float)*: Tiempo nominal en minutos sin tráfico.
- `edges[].current_time` *(float)*: Tiempo actual modificado por incidentes viales.
- `edges[].capacity` *(integer)*: Capacidad vehicular recomendada antes de saturación.
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
    "route": ["NODO_A", "NODO_C", "NODO_D", "NODO_F"],
    "travel_time": 18.0,
    "congestion_penalty": 6.3,
    "estimated_time": 24.3
  },
  "selfish": {
    "route": ["NODO_A", "NODO_C", "NODO_D", "NODO_F"],
    "travel_time": 18.0,
    "congestion_penalty": 13.74,
    "estimated_time": 31.74
  },
  "comparison": {
    "user_time_saved": 7.44,
    "user_improvement_pct": 23.44,
    "system_cost_optimized": 66.6,
    "system_cost_selfish": 80.48,
    "system_improvement_pct": 17.25
  },
  "flows": [
    {
      "name": "usuario",
      "origin": "NODO_A",
      "destination": "NODO_F",
      "vehicles": 1,
      "qaoa_route": ["NODO_A", "NODO_C", "NODO_D", "NODO_F"],
      "selfish_route": ["NODO_A", "NODO_C", "NODO_D", "NODO_F"]
    },
    {
      "name": "fondo_1",
      "origin": "NODO_B",
      "destination": "NODO_F",
      "vehicles": 20,
      "qaoa_route": ["NODO_B", "NODO_D", "NODO_F"],
      "selfish_route": ["NODO_B", "NODO_D", "NODO_F"]
    },
    {
      "name": "fondo_2",
      "origin": "NODO_A",
      "destination": "NODO_E",
      "vehicles": 30,
      "qaoa_route": ["NODO_A", "NODO_B", "NODO_E"],
      "selfish_route": ["NODO_A", "NODO_C", "NODO_E"]
    }
  ],
  "edge_loads": [
    {
      "source": "NODO_A",
      "target": "NODO_C",
      "capacity": 40,
      "event": "NORMAL",
      "vehicles_optimized": 1,
      "saturation_optimized": 0.025,
      "vehicles_selfish": 31,
      "saturation_selfish": 0.775
    }
  ],
  "quantum_telemetry": {
    "qubits_used": 6,
    "optimal_bitstring": "101001",
    "variables": ["x_0_0", "x_0_1", "x_1_0", "x_1_1", "x_2_0", "x_2_1"],
    "top_probabilities": [
      {
        "bitstring": "100110",
        "probability": 0.01031,
        "fval": 67.44,
        "feasible": true
      }
    ],
    "execution_time_ms": 178.88,
    "solver_used": "QAOA",
    "feasible": true,
    "qubo_scale": 1.0,
    "note": null
  },
  "total_time_ms": 179.33
}
```

#### Interpretación de Resultados y Comparativa
- **Ruta Egoísta (Dijkstra):** Cada conductor toma la ruta con menor tiempo base individual sin coordinarse. En el ejemplo, el usuario y el `fondo_2` eligen pasar por `NODO_A → NODO_C`, congestionando la vía central con 31 vehículos (saturación al 77.5%).
- **Ruta Optimizada (QAOA):** El algoritmo cuántico desacopla las trayectorias enviando al `fondo_2` por la vía periférica `A → B → E`. Esto ahorra un **23.44% de tiempo al usuario** y disminuye el costo global del sistema en un **17.25%**.
- **Telemetría Cuántica:**
  - `optimal_bitstring`: `101001` descompuesto en pares `[10][10][01]` indica que el usuario tomó la Ruta 1, el fondo 1 la Ruta 1, y el fondo 2 la Ruta 2.
  - `execution_time_ms`: Tiempo de ejecución del algoritmo cuántico en simulador (~180 ms).
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
