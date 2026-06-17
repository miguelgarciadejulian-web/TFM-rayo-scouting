# Rayo Vallecano — Herramienta de Dirección Deportiva y Scouting

Herramienta profesional en Python para apoyar la **planificación de la temporada 2026/2027** del Rayo Vallecano. Cubre los procesos descritos en el apartado *“2) Dirección Deportiva y Scouting”* del documento **TFM_25-26.pdf**.

Permite a la dirección deportiva:

- Analizar la plantilla actual (edad, contratos, salarios, valor de mercado).
- Identificar **necesidades deportivas** por posición y perfil.
- Detectar **posibles fichajes**, **ventas** y **cesiones**.
- Generar automáticamente **informes PDF profesionales** por jugador.
- Visualizar **dashboards interactivos** (Dash) con comparadores y simulador de mercado.
- Procesar **eventos OPTA (.json)** para análisis táctico y métricas avanzadas.
- Completar información faltante con **módulos de web scraping** (FBRef, FotMob, SofaScore, Transfermarkt).

---

## 1. Arquitectura general

```
rayo_scouting_tool/
├── config/                    # Parámetros globales (YAML)
│   ├── settings.yaml          # Rutas, ligas, temporada activa
│   ├── club_profile.yaml      # Presupuesto Rayo, masa salarial, ingresos
│   └── scouting_profiles.yaml # Perfiles por posición (ej. lateral derecho ofensivo)
├── data/
│   ├── raw/                   # Datos brutos (zips originales en /Datos)
│   ├── interim/               # Tras limpieza por liga/temporada
│   ├── processed/             # Master scouting consolidado (parquet)
│   ├── external/              # Scraping (Transfermarkt, FBRef, FotMob)
│   ├── opta_json/             # Eventos OPTA por partido
│   └── reports_out/           # PDFs generados
├── src/
│   ├── ingestion/             # Carga de zips, CSV, parquet
│   ├── etl/                   # Limpieza, normalización, unificación
│   ├── opta/                  # Parser OPTA JSON → eventos tabulares
│   ├── scraping/              # Selenium + BS4 para fuentes externas
│   ├── scouting/              # Filtros, percentiles, similitud, scoring
│   ├── squad/                 # Análisis plantilla Rayo
│   ├── economics/             # Modelo económico y simulador de mercado
│   ├── reports/               # Generación PDF (ReportLab + matplotlib)
│   ├── viz/                   # Radar, pizza, heatmaps, mapas tácticos
│   └── utils/                 # Logging, IO, validadores
├── notebooks/                 # Exploración y documentación viva
├── dashboard/                 # App Dash multipágina
│   ├── app.py
│   ├── pages/                 # plantilla, scouting, comparador, mercado
│   ├── components/            # filtros, tablas, gráficos reutilizables
│   └── assets/                # CSS, logos
├── scripts/                   # Pipelines de un comando (build_master, run_dashboard)
├── tests/
└── requirements.txt
```

**Principios de diseño**

- **Modularidad**: cada `src/<módulo>` es independiente, importable desde notebooks y Dash.
- **Configuración externa**: nada hardcodeado; todo en YAML.
- **Idempotencia**: los pipelines ETL se pueden re-ejecutar sin duplicar datos.
- **Trazabilidad**: cada jugador del *master* incluye `source`, `season`, `last_updated`.
- **Reutilización**: el código OPTA y de scraping de `/first class` se moderniza dentro de `src/opta` y `src/scraping`.

---

## 2. Carpeta `Datos/` — diagnóstico e ingestión

Contiene 6 ZIPs (~34 GB) con datasets por región: `testeo_ligas_europa.zip`, `_sudamerica`, `_asia`, `_norteamerica`, `_africa`, `_world`.

### Estrategia de ingestión

1. **No descomprimir todo a disco**. Usar `zipfile` en streaming para listar contenido y extraer sólo CSVs requeridos por liga/temporada (`src/ingestion/zip_reader.py`).
2. **Inferencia automática de esquema** (`src/etl/schema_inference.py`):
   - Detecta delimitador, encoding, columnas, dtypes.
   - Clasifica columnas en familias: identidad, demografía, contrato, métricas ofensivas, defensivas, de pase, GK, físicas, expected (xG/xA), posicionales.
3. **Normalización** (`src/etl/normalize.py`):
   - Unifica nombres de columnas a un esquema canónico (`config/canonical_schema.yaml`).
   - Convierte estadísticas por 90 minutos cuando faltan.
   - Resuelve duplicados (mismo jugador en varias ligas → prioridad última temporada).
4. **Construcción del Master Scouting** (`src/etl/build_master.py`):
   - Output: `data/processed/master_players.parquet`.
   - Una fila por (jugador, temporada).
   - Columnas mínimas: `player_id, name, dob, age, nationality, position, foot, team, league, country, season, minutes, market_value_eur, contract_end, salary_eur, source` + métricas.

### Relación entre datasets

- **Clave primaria sintética**: `player_id = slug(name) + '_' + dob` (cuando hay DOB) o `slug(name) + '_' + nationality`.
- **Tablas dimensionales**: `dim_leagues`, `dim_teams`, `dim_seasons` para joins limpios y filtros en Dash.

---

## 3. Carpeta `first class/` — qué se reutiliza

| Activo | Reutilización |
|---|---|
| `A_opta event mapping_eng.ipynb` | Base del parser `src/opta/parser.py`. Convierte JSON OPTA → DataFrame de eventos. |
| `try/transformers de opta/*.csv` | Tablas maestras OPTA (event types, qualifiers). Se mueven a `config/opta/`. |
| `Scraping_LaLiga_Teams.ipynb`, `2_match url scraping.ipynb` | Patrones Selenium → `src/scraping/{fbref,fotmob,sofascore}.py`. |
| `E1_simple goal dash.ipynb` | Plantilla de página Dash (filtros + gráfico + tabla) → `dashboard/pages/match_view.py`. |
| `trabajo2.ipynb` (xG, formaciones, mapas de pase) | Funciones de visualización táctica → `src/viz/tactical.py`. |
| `DATASET_LALIGA_COMPLETO.csv` | Dato de arranque para validar pipelines con LaLiga real. |

---

## 4. Procesamiento OPTA (.json)

Pipeline en `src/opta/`:

1. **`parser.py`** — Lee JSON (incluso envuelto en JSONP), recorre `liveData.event`, devuelve un DataFrame con columnas: `event_id, period_id, minute, second, team_id, player_id, type_id, type_name, x, y, end_x, end_y, outcome, qualifiers_dict, ...`.
2. **`enrich.py`** — Cruza con tablas de event types y qualifiers (`config/opta/`). Añade flags: `is_shot, is_pass, is_progressive, is_under_pressure, big_chance, xg_simple`.
3. **`metrics.py`** — Agrega a métricas por jugador y partido: `xG, xA, progressive_passes, pressures, ball_recoveries, defensive_actions, passes_into_box`. Estas métricas se suman al **master scouting** como features avanzadas.
4. **`pitch_maps.py`** — Genera mapas de tiros, pases, recuperaciones (usando `mplsoccer`) reutilizables tanto en PDF como en Dash.

**Integración**: los `.json` se depositan en `data/opta_json/`. El script `scripts/process_opta_batch.py` los procesa todos a parquet en `data/processed/opta_events.parquet`. Cada informe PDF de un jugador que tiene eventos OPTA disponibles incluye un mapa táctico.

---

## 5. Web scraping (fuentes complementarias)

Cuando faltan datos económicos o de mercado, `src/scraping/` cubre:

- **Transfermarkt** → valor de mercado, contrato, agente, historial de fichajes.
- **FBRef** → métricas avanzadas por 90 (xG, xA, progressive carries).
- **FotMob / SofaScore** → ratings, mapas de calor, alineaciones.
- **Capology / Salary Sport** → estimación salarial.

Patrón: `BaseScraper` (rate limiting, retries, cache local en `data/external/cache/`) + scrapers específicos. Reutiliza la lógica Selenium ya presente en `first class/2_match url scraping.ipynb`.

---

## 6. Módulo de scouting (`src/scouting/`)

- **`filters.py`** — Filtros encadenables: posición, edad, liga, nacionalidad, minutos mínimos, valor de mercado ≤ X, contrato terminando en ≤ N meses.
- **`percentiles.py`** — Percentiles por posición y liga (peer group). Imprescindible para comparar entre ligas.
- **`similarity.py`** — Distancia coseno sobre vector estandarizado de métricas → “jugadores parecidos a Isi Palazón pero más jóvenes y baratos”.
- **`scoring.py`** — Score compuesto por **perfil táctico** definido en `config/scouting_profiles.yaml` (ej.: *lateral derecho ofensivo* = 0.3·crosses + 0.25·progressive_carries + 0.2·defensive_actions + 0.15·xA + 0.1·duels_won).
- **`fit.py`** — *Encaje táctico* en el Rayo: bonus si juega el sistema base (4-2-3-1/4-3-3 de Íñigo Pérez), penalización si el perfil duplica el de un titular indiscutible.

---

## 7. Plantilla, economía y simulador (`src/squad`, `src/economics`)

- **`squad/current_squad.py`** — Carga plantilla 2025/26 con altas/bajas del verano 2026. Configurable en `config/club_profile.yaml` (ver más abajo).
- **`squad/needs.py`** — Detecta huecos: posiciones con <2 jugadores, edad media alta, contratos finalizando.
- **`economics/budget.py`** — Modela ingresos (TV, ventas, Europa, premios, patrocinadores) y gastos (masa salarial, amortizaciones).
- **`economics/market_sim.py`** — Simulador: dado un fichaje (coste + salario + años) y posibles ventas/cesiones, calcula impacto en balance y *fair play financiero*.

### Contexto financiero — Rayo Vallecano 2026/27 (parámetros editables en `config/club_profile.yaml`)

> Valores aproximados, deben validarse con la dirección deportiva.

- Ingresos TV LaLiga: **~45–55 M€** (en función de clasificación 2025/26).
- Premios deportivos + Conference League (si aplica): **5–10 M€**.
- Patrocinadores + comercial: **~12–15 M€**.
- Ventas estimadas: **15–25 M€**.
- Masa salarial bruta objetivo: **~50–55 M€** (límite LaLiga).
- Presupuesto fichajes neto: **8–12 M€**, ampliable con ventas.

---

## 8. Informes PDF (`src/reports/`)

Cada informe se genera con `reportlab` + figuras matplotlib precalculadas:

1. **Portada**: foto, datos personales, equipo, posición, valor.
2. **Resumen ejecutivo**: recomendación final (Comprar / Observar / Descartar) + nivel de confianza.
3. **Métricas clave + percentiles** (tabla y barras).
4. **Radar chart** vs media de la posición en LaLiga.
5. **Mapas OPTA** (tiros, pases progresivos, acciones defensivas) si existe data.
6. **Fortalezas / Debilidades** generadas automáticamente desde percentiles (>80 / <30).
7. **Encaje táctico** en el sistema del Rayo + comparativa con titular actual.
8. **Viabilidad económica**: coste estimado, salario, impacto en presupuesto.
9. **Jugadores similares** (top-5 por similitud).

Punto de entrada: `from src.reports.player_report import generate_pdf; generate_pdf(player_id, out_path)`.

---

## 9. Dashboard Dash (`dashboard/`)

App multipágina (Dash Pages):

- **/plantilla** — Tabla de plantilla, pirámide de edad, gantt de contratos.
- **/scouting** — Buscador con filtros laterales + tabla ordenable + botón “Generar informe PDF”.
- **/comparador** — Selector multi-jugador + radar overlay + tabla de percentiles.
- **/mercado** — Simulador: arrastrar jugadores a “Comprar / Vender / Ceder” y ver impacto económico.
- **/partidos** — Visor OPTA por partido (heredado de `E1_simple goal dash.ipynb`).

Diseño moderno con Dash Bootstrap Components, navbar lateral, tema oscuro Rayo (blanco/rojo).

---

## 10. Cómo ejecutar

```bash
# 1. Crear entorno
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt

# 2. Ingestar Datos/ → data/processed/master_players.parquet
python scripts/build_master.py

# 3. (Opcional) Procesar JSONs OPTA disponibles
python scripts/process_opta_batch.py

# 4. (Opcional) Scraping de refuerzo
python scripts/scrape_market_values.py

# 5. Lanzar dashboard
python dashboard/app.py   # http://127.0.0.1:8050

# 6. Generar un informe PDF puntual
python scripts/generate_report.py --player "Iñaki Williams"
```

Para desarrollo:

```bash
jupyter lab notebooks/
```

---

## 11. Próximos pasos sugeridos

1. Validar `config/club_profile.yaml` con cifras reales de la dirección deportiva.
2. Definir 8–10 **perfiles de scouting** en `config/scouting_profiles.yaml` alineados con el modelo de juego de Íñigo Pérez.
3. Ejecutar `build_master.py` sobre el ZIP de Europa primero (peer group más relevante).
4. Cargar los JSON OPTA disponibles de LaLiga 2025/26 para enriquecer la plantilla actual.
5. Iterar la plantilla del informe PDF con un caso real (ej. lateral derecho objetivo).
