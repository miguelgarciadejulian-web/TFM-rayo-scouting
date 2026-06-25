<div align="center">

# ⚡ Rayo Vallecano — Herramienta de Dirección Deportiva y Scouting

**Plataforma de análisis para la planificación deportiva, económica y de scouting de la temporada 2026/2027**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dash](https://img.shields.io/badge/Dash-Plotly-3F4F75?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![License](https://img.shields.io/badge/Uso-Acad%C3%A9mico%20(TFM)-E30613)](#licencia)

*Trabajo de Fin de Máster — Máster en Big Data Deportivo · Universidad Europea*

</div>

---

## 📑 Índice

1. [Descripción del proyecto](#1-descripción-del-proyecto)
2. [Objetivos](#2-objetivos)
3. [Características principales](#3-características-principales)
4. [Arquitectura de la aplicación](#4-arquitectura-de-la-aplicación)
5. [Tecnologías y librerías](#5-tecnologías-y-librerías)
6. [Estructura del proyecto](#6-estructura-del-proyecto)
7. [Requisitos previos](#7-requisitos-previos)
8. [Instalación paso a paso](#8-instalación-paso-a-paso)
9. [Configuración](#9-configuración)
10. [Cómo ejecutar la aplicación](#10-cómo-ejecutar-la-aplicación)
11. [Explicación de las carpetas](#11-explicación-de-las-carpetas)
12. [Metodología de los cálculos](#12-metodología-de-los-cálculos)
13. [Capturas y referencias](#13-capturas-y-referencias)
14. [Posibles mejoras futuras](#14-posibles-mejoras-futuras)
15. [Autor](#15-autor)

---

## 1. Descripción del proyecto

Esta herramienta es una **aplicación web de apoyo a la decisión** para la dirección deportiva y el cuerpo técnico del **Rayo Vallecano**. Centraliza, en un único panel de control, toda la información necesaria para tres procesos clave de la planificación de una temporada:

- **Análisis de la plantilla propia** — estado, edades, contratos, valor y rendimiento.
- **Scouting de fichajes** — exploración de más de **57.000 registros** de jugador-temporada con percentiles, perfiles tácticos y un índice de encaje con el club.
- **Estrategia deportiva y económica** — decisiones de renovación, casting de entrenadores, control de la masa salarial y simulación de operaciones.

Toda la inteligencia del sistema (perfiles de rol, encaje, scores y recomendaciones) se calcula **automáticamente por código** a partir de datos reales (OPTA y Transfermarkt); no hay valoraciones escritas a mano. El resultado es una plataforma reproducible que traduce grandes volúmenes de datos en información accionable para una dirección deportiva.

---

## 2. Objetivos

- **Unificar** en una sola herramienta el análisis de plantilla, el scouting y la planificación económica del club.
- **Automatizar** la clasificación de jugadores por rol y estilo a partir de sus métricas de juego, evitando juicios subjetivos.
- **Cuantificar el encaje** de cualquier jugador o entrenador con la identidad deportiva del Rayo mediante índices objetivos y explicables.
- **Detectar de forma dinámica** las necesidades de la plantilla (qué posiciones faltan, sobran o deben reforzarse).
- **Soportar la toma de decisiones** sobre fichajes, renovaciones y ventas con escenarios económicos y un control en tiempo real del límite salarial.
- **Generar informes profesionales** (PDF) listos para presentar al cuerpo técnico y la dirección deportiva.
- **Garantizar la reproducibilidad**: cualquier usuario puede clonar el repositorio, instalar las dependencias y obtener exactamente la misma herramienta funcionando.

---

## 3. Características principales

- **Dashboard web multipágina** con 9 módulos y un sistema de diseño coherente (identidad visual del Rayo: rojo `#E30613`, blanco y negro).
- **Base de scouting masiva**: ~57.000 jugador-temporada (2021–2026), ~11.800 jugadores de la temporada actual y ~17.400 registros económicos.
- **Clasificación automática de rol y estilo** por jugador a partir de percentiles OPTA.
- **Índice "Fit Rayo" (0–100)** que combina rendimiento, encaje económico, perfil de edad y disponibilidad contractual.
- **Motor de renovaciones** con recomendación automática (renovar / negociar / vender / ceder / proteger valor) y estimación salarial.
- **ADN Rayo dinámico**: 7 ejes de estilo de juego calculados desde datos OPTA reales.
- **Casting de entrenadores** con score de encaje táctico y análisis de riesgos.
- **Simuladores económicos**: impacto de fichajes/ventas/cesiones sobre la masa salarial y el límite LaLiga.
- **Buscador server-side** tolerante a tildes y errores tipográficos (~7 ms por búsqueda).
- **Informes PDF** con tema corporativo, descargables desde la propia aplicación.

---

## 4. Arquitectura de la aplicación

La aplicación sigue una **arquitectura por capas** que separa la presentación (Dash) de la lógica de negocio (`src/`) y de los datos (`data/`, `config/`):

```
+--------------------------------------------------------------+
|  CAPA DE PRESENTACION  -  dashboard/                         |
|  app.py (entry point, routing multipagina)                   |
|  pages/ (9 vistas)   components/ (UI reutilizable)           |
|  data_cache.py (cache en memoria de los datasets)            |
+-------------------------------+------------------------------+
                                |  importa
+-------------------------------v------------------------------+
|  CAPA DE LOGICA / DOMINIO  -  src/                           |
|  profiling/ -> rol y estilo de jugador y entrenador          |
|  fit/       -> encaje jugador/entrenador, renovaciones, riesgo|
|  scouting/  -> comparador y Fit Rayo                         |
|  squad/     -> necesidades dinamicas de plantilla            |
|  reports/   -> generacion de PDF                             |
|  utils/     -> configuracion, mercado, ligas, rendimiento    |
|  opta/      -> parser de los datos OPTA                      |
+-------------------------------+------------------------------+
                                |  lee
+-------------------------------v------------------------------+
|  CAPA DE DATOS                                               |
|  config/ (YAML/CSV de configuracion y datos del club)        |
|  data/processed/ (.parquet y .json calculados)               |
|  scripts/ (ETL: regeneran los datasets desde las fuentes)    |
+--------------------------------------------------------------+
```

**Flujo de datos**: los `scripts/` realizan el ETL (descarga de Transfermarkt, parseo de OPTA, construcción de los datasets maestros) → generan los `.parquet`/`.json` en `data/processed/` → la app los carga **una sola vez** en memoria mediante `dashboard/data_cache.py` → cada página los consume y delega los cálculos en los módulos de `src/`. La interfaz nunca recalcula datos pesados en cada interacción: se apoya en cachés (`lru_cache`, caché global con TTL) para mantener la fluidez.

---

## 5. Tecnologías y librerías

| Ámbito | Tecnología | Uso en el proyecto |
|--------|-----------|---------------------|
| Lenguaje | **Python 3.10+** | Todo el backend y la lógica |
| Web / UI | **Dash** + **dash-bootstrap-components** | Framework del dashboard multipágina |
| Visualización | **Plotly** | Radares, donuts, barras, strip charts interactivos |
| Datos | **pandas**, **numpy** | Manipulación y cálculo numérico |
| Almacenamiento | **PyArrow** (Parquet) | Formato columnar de los datasets |
| Configuración | **PyYAML** | Carga de `config/*.yaml` |
| Machine Learning | **scikit-learn**, **SciPy** | `StandardScaler` y similitud coseno (comparador) |
| Gráficos para PDF | **Matplotlib** (backend Agg) | Radares y *gauges* embebidos en los informes |
| Informes | **ReportLab**, **xhtml2pdf**, **Pillow** | Generación de PDF (compatible con Windows) |
| Búsqueda | **Unidecode** | Búsqueda tolerante a tildes |
| ETL / scraping | **requests**, **BeautifulSoup**, **cloudscraper**, **tqdm** | Solo en `scripts/` para regenerar datos |

> El detalle exacto de versiones está en [`requirements.txt`](requirements.txt). WeasyPrint es opcional (solo se usa en Linux/Mac; en Windows la app recurre automáticamente a xhtml2pdf).

---

## 6. Estructura del proyecto

```
rayo_scouting_tool/
├── INICIAR_HERRAMIENTA.bat      # Arranque con un doble clic (Windows)
├── requirements.txt             # Dependencias del proyecto
├── README.md
│
├── config/                      # Configuración y datos del club (versionados)
│   ├── settings.yaml            # Rutas, temporada activa, prioridad de ligas
│   ├── club_profile.yaml        # Plantilla 25/26, contratos, salarios, presupuesto
│   ├── coaches.yaml             # Candidatos a entrenador con metadatos
│   ├── coach_history.yaml       # Historial de equipos por entrenador
│   ├── rayo_dna.yaml            # ADN Rayo objetivo (ejes de estilo)
│   ├── salary_estimates.yaml    # Referencias salariales por liga/club
│   ├── scouting_profiles.yaml   # Perfiles tácticos de búsqueda
│   └── opta/                    # Tablas maestras OPTA (tipos de evento/qualifier)
│
├── data/
│   └── processed/               # Datasets calculados que consume la app
│       ├── player_seasons_enriched.parquet   # ~57k filas — base de scouting
│       ├── master_players.parquet            # jugadores con métricas por temporada
│       ├── player_economic.parquet           # datos económicos (TM)
│       ├── team_seasons.parquet              # stats OPTA por equipo/temporada
│       ├── coach_profiles.json               # perfiles de entrenadores calculados
│       ├── squad_profile.json                # perfil dinámico de la plantilla
│       └── signing_shortlists.json           # shortlists por posición
│
├── dashboard/                   # Capa de presentación (Dash)
│   ├── app.py                   # Entry point + routing + barra lateral
│   ├── data_cache.py            # Caché global de datasets en memoria
│   ├── pages/                   # Una vista por archivo (9 páginas)
│   │   ├── home.py              # Panel de dirección deportiva
│   │   ├── plantilla.py         # Plantilla 25/26
│   │   ├── scouting.py          # Buscador de candidatos
│   │   ├── jugador.py           # Perfil completo de jugador + PDF
│   │   ├── comparador.py        # Comparativa de jugadores
│   │   ├── decisiones.py        # Fichajes / Renovaciones / Entrenadores
│   │   ├── entrenadores.py      # Casting técnico + ADN Rayo
│   │   ├── finanzas.py          # Masa salarial y simuladores
│   │   └── criterios.py         # Metodología (auto-generada del código)
│   ├── components/              # UI reutilizable (tarjetas, radar, tema)
│   └── assets/                  # CSS e imágenes
│
├── src/                         # Capa de lógica / dominio (sin dependencia de UI)
│   ├── profiling/               # Clasificación de rol y estilo
│   ├── fit/                     # Encaje, decisiones, renovaciones, riesgo cláusula
│   ├── scouting/                # Comparador y Fit Rayo
│   ├── squad/                   # Necesidades dinámicas de plantilla
│   ├── reports/                 # Generadores de PDF (jugador, entrenador, comparador)
│   ├── utils/                   # Configuración, mercado, ligas, rendimiento
│   └── opta/                    # Parser OPTA
│
├── scripts/                     # ETL — regeneran los datasets de data/processed/
└── tests/                       # Pruebas del motor de perfilado y encaje
```

---

## 7. Requisitos previos

- **Python 3.10 o superior** (probado hasta 3.12). En Windows se recomienda el instalador oficial de [python.org](https://www.python.org/downloads/) marcando *"Add Python to PATH"*, o una distribución **Anaconda/Miniconda**.
- **pip** (incluido con Python).
- **~500 MB de espacio** libre y conexión a internet la primera vez (para instalar las dependencias).
- **Git** para clonar el repositorio.

No se necesita ninguna base de datos ni servicio externo: la herramienta funciona en local y los datos viajan dentro del repositorio.

---

## 8. Instalación paso a paso

```bash
# 1) Clonar el repositorio
git clone https://github.com/miguelgarciadejulian-web/TFM-rayo-scouting.git
cd TFM-rayo-scouting

# 2) (Opcional, recomendado) crear un entorno virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / Mac:
source .venv/bin/activate

# 3) Instalar las dependencias
pip install -r requirements.txt
```

En **Windows** los pasos 2 y 3 no son obligatorios: el script `INICIAR_HERRAMIENTA.bat` instala las dependencias automáticamente la primera vez (ver [sección 10](#10-cómo-ejecutar-la-aplicación)).

---

## 9. Configuración

La configuración vive en la carpeta `config/` y **no requiere ningún ajuste para arrancar**. Los archivos más relevantes:

- **`settings.yaml`** — temporada activa, rutas de datos (relativas a la raíz del proyecto) y prioridad de ligas. Las rutas se resuelven automáticamente, por lo que el proyecto es **portable entre equipos** sin tocar nada.
- **`club_profile.yaml`** — plantilla actual del Rayo, contratos, salarios, formación base y presupuesto. Es la principal fuente que querrás actualizar al cambiar de temporada.
- **`coaches.yaml`** / **`coach_history.yaml`** — candidatos a entrenador y su historial.
- **`rayo_dna.yaml`** — pesos del ADN Rayo objetivo.
- **`salary_estimates.yaml`** — referencias salariales para los simuladores.

Las ediciones que el usuario realiza dentro de la app (salarios, notas, fotos, posición lateral) se guardan en `data/processed/*.json` y persisten entre sesiones.

---

## 10. Cómo ejecutar la aplicación

### Opción A — Windows (recomendada): `INICIAR_HERRAMIENTA.bat`

Hecha para que **cualquier usuario** ponga en marcha la herramienta sin conocer ningún comando:

1. Haz **doble clic** en `INICIAR_HERRAMIENTA.bat`.
2. La primera vez, el script detecta Python (Anaconda, el lanzador `py` o `python` del PATH) e **instala automáticamente las dependencias** (puede tardar unos minutos; solo ocurre una vez).
3. Cuando aparezca el mensaje, abre en el navegador **http://127.0.0.1:8050**.
4. Para detener la herramienta, cierra la ventana negra o pulsa `Ctrl + C`.

> En arranques posteriores no se reinstala nada (existe un marcador `.deps_ok`). Si alguna vez quieres forzar la reinstalación, borra ese archivo.

### Opción B — Línea de comandos (cualquier sistema operativo)

```bash
python -m dashboard.app
# La app queda escuchando en http://127.0.0.1:8050
```

---

## 11. Explicación de las carpetas

| Carpeta | Responsabilidad |
|---------|-----------------|
| **`config/`** | Toda la configuración y los datos curados del club (YAML/CSV). Es la "fuente de verdad" editable a mano. |
| **`data/processed/`** | Datasets calculados (`.parquet`/`.json`) que consume la app. Los `.parquet` de runtime se versionan para que la herramienta funcione tras clonar; los volcados crudos de API (grandes) se ignoran y se regeneran con `scripts/`. |
| **`dashboard/`** | La aplicación Dash: punto de entrada, páginas, componentes y caché. **Aquí está la interfaz.** |
| **`dashboard/pages/`** | Una vista por archivo. Dash las registra automáticamente (`use_pages`), de modo que añadir una página es tan simple como crear un nuevo archivo. |
| **`dashboard/components/`** | Bloques de interfaz reutilizables (tarjeta de jugador, detalle, tema de gráficos, normalización de nombres). |
| **`src/`** | La lógica de negocio, **sin ninguna dependencia de la interfaz**. Se puede probar y reutilizar de forma aislada (de hecho, los `scripts/` y `tests/` la usan). |
| **`scripts/`** | Procesos ETL que reconstruyen los datasets desde las fuentes (Transfermarkt, OPTA). No se ejecutan para usar la app, solo para actualizar los datos. |
| **`tests/`** | Pruebas automatizadas del motor de perfilado y encaje (`pytest`). |

---

## 12. Metodología de los cálculos

Todos los índices son **deterministas, explicables y derivados de datos reales**. Los principales:

**Perfil de jugador (rol y estilo).** Cada jugador-temporada se clasifica en un rol principal (y roles secundarios) comparando sus percentiles OPTA contra el resto de jugadores de su posición. El `primary_score` (0–100) refleja cómo de buen exponente es de ese rol.

**Fit Rayo del comparador (0–100).** Combina cuatro componentes: **rendimiento (35 %)**, **encaje económico (25 %)** —valor de mercado frente a la horquilla de inversión del club—, **perfil de edad (20 %)** —curva edad/posición— y **disponibilidad contractual (20 %)** —contrato expirante, agente libre, cesión con opción, etc.

**Encaje de fichaje (`player_fit`).** Para el scouting, valora la **compatibilidad con la plantilla** (¿cubre un hueco o sobra ese perfil?), la **compatibilidad con el entrenador** (afinidad del rol con el estilo del técnico actual, derivada dinámicamente), el **valor estratégico** y el **impacto deportivo** esperado.

**Necesidades de plantilla (`needs`).** A partir de la formación base del `club_profile.yaml` se deriva una plantilla objetivo de 25 jugadores y se compara con los roles reales de la plantilla para marcar qué perfiles **faltan**, cuáles hay que **reforzar** y cuáles están **sobre-representados** (semáforo por posición).

**Decisión de renovación (0–100).** Pondera **rendimiento (40 %)**, **edad y ciclo vital (20 %)**, **situación económica (20 %)** y **situación contractual (20 %)**, y emite una de cinco recomendaciones (renovar / no renovar / vender / renovar y ceder / renovar para proteger valor) con su nivel de confianza.

**Encaje de entrenador (`coach_fit`).** Mide la cercanía del estilo del técnico al **ADN Rayo objetivo**, su experiencia en LaLiga y el contexto económico/contractual, devolviendo un score 0–100 con pros, contras y riesgos desglosados.

**ADN Rayo dinámico.** Siete ejes de estilo (presión alta, posesión, solidez defensiva, tendencia ofensiva, verticalidad, intensidad defensiva y uso de transiciones) calculados con percentiles a partir de los datos OPTA por equipo, no de valores fijos.

**Riesgo de cláusula.** Modelo de cuatro niveles (muy alto / alto / medio / bajo) según la relación entre la cláusula, el valor de mercado y la situación del jugador.

> La pestaña **Criterios** de la propia aplicación genera esta metodología **automáticamente desde el código**, de modo que la documentación y el comportamiento real nunca se desincronizan.

---

## 13. Capturas y referencias

> Las capturas de pantalla de cada módulo pueden añadirse en `dashboard/assets/` y referenciarse aquí. Mientras tanto, la mejor forma de conocer la herramienta es ejecutarla y recorrer sus 9 módulos desde la barra lateral.

**Módulos del dashboard**: Inicio · Plantilla · Scouting · Perfil de jugador · Comparador · Decisiones · Entrenadores · Finanzas · Criterios.

**Fuentes de datos**: datos de evento **OPTA** (temporadas 2021–2026) y **Transfermarkt** (valores de mercado, contratos, fotos), complementados con datos curados del club en `config/`.

---

## 14. Posibles mejoras futuras

- **Persistencia en base de datos** (PostgreSQL/SQLite) en lugar de ficheros, para edición concurrente por varios usuarios.
- **Autenticación y roles** (dirección deportiva, scouting, cuerpo técnico) con vistas y permisos diferenciados.
- **Actualización automática de datos** mediante tareas programadas que ejecuten el ETL y refresquen los `.parquet`.
- **Modelos predictivos** de revalorización de jugadores y de rendimiento esperado (más allá de los índices por reglas actuales).
- **Despliegue en la nube** (contenedor Docker + servicio gestionado) para acceso remoto del staff.
- **Tests de integración** que cubran las páginas y los callbacks de Dash, además del motor de dominio.
- **Internacionalización** de la interfaz y exportación de informes en varios idiomas.

---

## 15. Autor

**Miguel García de Julián**
Trabajo de Fin de Máster — Máster en Big Data Deportivo
**Universidad Europea** · 2026

📧 miguelgarciadejulian@gmail.com
🔗 [github.com/miguelgarciadejulian-web/TFM-rayo-scouting](https://github.com/miguelgarciadejulian-web/TFM-rayo-scouting)

---

## Licencia

Proyecto de carácter **académico** desarrollado como Trabajo de Fin de Máster. El escudo y la identidad visual del Rayo Vallecano se utilizan únicamente con fines educativos y de demostración. Los datos de OPTA y Transfermarkt pertenecen a sus respectivos propietarios.
