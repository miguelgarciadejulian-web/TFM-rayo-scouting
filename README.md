# Rayo Vallecano — Herramienta de Dirección Deportiva y Scouting

Herramienta profesional en Python/Dash para apoyar la **planificación deportiva y económica 2026/2027** del Rayo Vallecano. Cubre los procesos de *Dirección Deportiva y Scouting* del TFM.

> **Diseño visual v3** — Panel de control moderno con hero gradiente por módulo, KPI cards con iconos en gradiente, filtros como cards blancas y gráficos 2×2. Mismo sistema de diseño en las 7 páginas del dashboard.

---

## Lanzar la aplicación

```bash
# Instalar dependencias
pip install -r requirements.txt

# Lanzar el dashboard
python dashboard/app.py   # http://127.0.0.1:8050
```

---

## Módulos del dashboard

### Inicio (`/`)
Panel de control moderno con hero Rayo (gradiente rojo/negro), 3 métricas macro en el hero (jugadores, valor de mercado, candidatos), 6 KPI cards coloreadas, alertas dinámicas tipo pill, y layout 8+4: gráficos 2×2 a la izquierda + tarjetas de módulo con gradiente de color a la derecha.

### Plantilla (`/plantilla`)
Hero azul con métricas de plantilla. KPI cards para jugadores, valor total, presupuesto, contratos urgentes y cedidos. Visualizaciones: strip chart de edades por línea, donut por posición, barras de vencimientos y valor de mercado top-12. Cada jugador es clicable → perfil. Salarios editables con guardado en YAML. Panel de necesidades 2026/27 con semáforo por posición.

### Scouting (`/scouting`)
Hero verde. Panel de filtros como card blanca (posición, tipología, liga, equipo, pierna, edad, valor, minutos). Tabla con >54.000 jugadores con percentiles y Fit Rayo. Clic en fila navega al perfil. Buscador fuzzy tolerante a tildes y errores tipográficos.

### Perfil de jugador (`/jugador`)
Perfil completo por jugador:
- Datos biográficos y de mercado (con edición manual persistente)
- **Fit Rayo** detallado: rendimiento, encaje económico, perfil de edad, disponibilidad contractual
- **Radar de rol** y clasificación automática (rol principal, estilo, roles secundarios)
- **Percentiles por métrica** vs jugadores de su posición (histórico completo)
- **Evolución por temporada** (goles, asistencias, minutos, métricas clave)
- **Riesgo de cláusula** (4 niveles)
- Notas internas y foto personalizable
- **PDF profesional** descargable (tema Rayo dark)

El buscador funciona con búsqueda en servidor: escribe 2+ caracteres y aparecen resultados al instante. Detecta traspasos de invierno mostrando el club con más minutos en la última temporada.

### Comparador (`/comparador`)
Hero púrpura. Panel de selección con filtro de posición + dropdown de candidatos externos + jugadores del Rayo. Botón "Comparar" con gradiente púrpura. Radar overlay, tabla de percentiles, indicadores de fortalezas/debilidades relativas. Fit Rayo 0–100 calculado automáticamente.

### Decisiones (`/decisiones`)
Hero ámbar con stats de fichas urgentes, renovaciones críticas y candidatos a salida. Tres pestañas con emoji e iconos:
- **🎯 Fichajes**: Explorador de candidatos por perfil con filtros avanzados (liga, valor, edad, contrato, grandes clubes)
- **📋 Renovaciones**: Decisión automática (score 0-100: renovar / negociar / dejar salir) con estimación salarial por jugador
- **🧑‍🏫 Entrenadores**: Top 3 candidatos al banquillo con score y enlace al módulo completo

### Entrenadores (`/entrenadores`)
Hero naranja con técnicos/libres/mejor encaje. KPI cards de casting. ADN Rayo calculado desde datos OPTA reales (7 ejes: presión alta, posesión, solidez defensiva, tendencia ofensiva, verticalidad, intensidad defensiva, uso de transiciones). Panel de necesidades de plantilla siempre visible. Filtros (disponibilidad, estilo, Fit Rayo mínimo) como card blanca. Análisis de candidato con radar y PDF descargable.

### Finanzas (`/finanzas`)
Hero esmeralda con masa salarial, % del límite FFP y presupuesto neto. Cinco pestañas:
- **💶 Salarios**: Tabla editable con simulación en tiempo real de impacto en masa salarial y límite LaLiga
- **📊 Presupuesto**: Ingresos vs gastos estimados con gráficos de evolución
- **🎯 Riesgo cláusulas**: Mapa de riesgo (muy alto / alto / medio / bajo) por jugador
- **🔀 Simulador Económico**: Escenarios de fichaje/venta/cesión con impacto financiero
- **📋 Simulador Fichajes**: Evaluación inteligente de operaciones de compra/venta con score de éxito (0-100), factores desglosados (precio vs MV, importancia, edad, necesidad de plantilla) y veredicto automático

### Criterios (`/criterios`)
Hero carmesí. Metodología completa de cálculo de scores de jugadores y entrenadores, generada automáticamente desde el código (siempre sincronizada). Pesos por rol, ejes de estilo de entrenador, ADN Rayo objetivo.

---

## Arquitectura

```
rayo_scouting_tool/
├── config/
│   ├── settings.yaml              # Rutas, temporada activa, ligas
│   ├── club_profile.yaml          # Presupuesto, masa salarial, plantilla 25/26
│   ├── coaches.yaml               # Candidatos a entrenador con metadatos
│   ├── coach_tenures.csv          # Historial de equipos por entrenador
│   ├── rayo_dna.yaml              # Pesos ADN Rayo objetivo
│   ├── salary_estimates.yaml      # Estimaciones salariales por liga y club
│   └── opta/                      # Tablas maestras OPTA
├── data/
│   ├── processed/
│   │   ├── player_seasons_enriched.parquet   # ~54k filas, base de scouting
│   │   ├── master_players.parquet            # Jugadores únicos con métricas
│   │   ├── market_values.csv                 # Valores TM + contratos
│   │   ├── coach_profiles.json               # Perfiles calculados de entrenadores
│   │   ├── squad_profile.json                # Perfil dinámico plantilla Rayo
│   │   └── signing_shortlists.json           # Shortlists por posición
│   └── reports_out/               # PDFs generados
├── dashboard/
│   ├── app.py                     # Entry point Dash multipágina
│   ├── pages/
│   │   ├── home.py                # Panel de control moderno — hero Rayo
│   │   ├── plantilla.py           # Plantilla 25/26 — hero azul
│   │   ├── scouting.py            # Buscador — hero verde
│   │   ├── jugador.py             # Perfil completo + PDF
│   │   ├── comparador.py          # Comparador — hero púrpura
│   │   ├── decisiones.py          # Fichajes/Renovaciones/Entrenadores — hero ámbar
│   │   ├── entrenadores.py        # Casting técnicos — hero naranja
│   │   ├── finanzas.py            # Simulador financiero — hero esmeralda
│   │   └── criterios.py           # Metodología — hero carmesí
│   └── components/
│       ├── player_detail.py       # Perfil jugador (percentiles, radar, evolución)
│       ├── profile_card.py        # Tarjeta resumen jugador
│       ├── criteria_block.py      # Bloque de criterios reutilizable
│       ├── display_names.py       # Normalización posición/liga
│       └── chart_theme.py         # Tema Plotly profesional
├── src/
│   ├── fit/
│   │   ├── dynamic_dna.py         # ADN Rayo desde datos OPTA reales
│   │   ├── coach_fit.py           # Score encaje entrenador × Rayo
│   │   ├── player_fit.py          # Score Fit Rayo por jugador
│   │   ├── clause_risk.py         # Modelo riesgo de cláusula (4 niveles)
│   │   ├── decisions.py           # Motor de decisiones deportivas
│   │   ├── renewal_decision.py    # Decisión automática renovación
│   │   └── renewal_engine.py      # Motor de renovaciones con estimación salarial
│   ├── profiling/
│   │   ├── player_profile.py      # Clasificación de rol y estilo por jugador
│   │   └── coach_style.py         # Estilo táctico de entrenador desde historial
│   ├── reports/
│   │   ├── player_dossier.py      # PDF profesional jugador (tema Rayo dark)
│   │   └── coach_dossier.py       # PDF profesional entrenador (tema Rayo dark)
│   ├── scouting/
│   │   ├── scoring.py             # Score compuesto por perfil táctico
│   │   └── comparator.py          # Comparador de candidatos a fichaje
│   ├── squad/
│   │   └── needs.py               # Detección dinámica de necesidades de plantilla
│   ├── economics/
│   │   └── budget.py              # Modelo económico y simulador
│   ├── etl/
│   │   └── normalize.py           # Normalización de nombres, ligas, posiciones
│   ├── utils/
│   │   ├── config.py              # Carga YAML y parámetros globales
│   │   ├── leagues.py             # Normalización nombres de liga
│   │   ├── market.py              # Valores de mercado y contratos (TM)
│   │   └── lateral_position.py    # Inferencia posición lateral (LI/LD)
│   └── opta/
│       └── parser.py              # Parser OPTA JSON → DataFrame
└── scripts/
    ├── build_profiles.py          # Reconstruye coach_profiles.json
    └── fetch_tm_api.py            # ETL valores de mercado desde Transfermarkt
```

---

## Fuentes de datos

| Fuente | Uso |
|--------|-----|
| Datos OPTA (ZIP) | Base de scouting: ~54k filas × temporadas 2021–2026 |
| `config/coaches.yaml` | Candidatos a entrenador con metadatos curados |
| `config/club_profile.yaml` | Plantilla Rayo, contratos, salarios, presupuesto |
| `config/salary_estimates.yaml` | Salarios de referencia por liga, club y posición |
| Transfermarkt (API) | Valores de mercado, fotos, historial, edad, pie dominante |
| Overrides manuales | Ediciones in-app (salarios, fotos, notas, posición lateral) |

---

## Decisiones técnicas destacadas

- **Sistema de diseño v3**: Hero con gradiente por módulo (color único para cada página), KPI cards con iconos en gradiente, filtros como cards blancas con label de color, layout consistente en las 7 páginas. Sin librerías de UI extra — CSS inline en Dash.
- **Dedup de traspasos de invierno**: `player_seasons_enriched.parquet` puede tener dos filas para el mismo jugador y temporada (cambio de equipo a mitad de temporada). El sistema ordena por `[_ord, minutes]` descendente y toma la primera fila → siempre muestra el equipo con más minutos jugados.
- **Valores de mercado desde TM**: `src.utils.market.get_value(name)` lee `market_values.csv` y devuelve MV, edad, posición, contrato y foto para cualquier jugador. El equipo mostrado siempre viene del enriched (dónde jugó realmente), nunca del campo `club` de TM.
- **Simulador de fichajes con score dinámico**: `_evaluate_sale` y `_evaluate_buy` calculan un score 0-100 con 4 factores (precio vs MV, importancia/minutos, edad y necesidad de plantilla) y devuelven razones con fórmulas y puntos visibles al usuario.
- **Codificación UTF-8 explícita** en todos los `.py` para compatibilidad con Windows (cp1252).
- **Búsqueda server-side** en el perfil de jugador: lookup table cacheada con `lru_cache` (~1.2s arranque, ~7ms por búsqueda).
- **ADN Rayo dinámico**: `dynamic_dna.py` calcula los 7 ejes del ADN desde datos OPTA reales, no YAML estáticos. Percentiles con `(vals <= raw).mean() * 100`; los ceros se tratan como dato ausente.
- **PDFs con tema Rayo dark**: generados con ReportLab, diseño ejecutivo profesional.
- **Estimaciones salariales**: `salary_estimates.yaml` contiene referencias por liga y club para que el simulador de renovaciones sugiera rangos salariales realistas.
