<div align="center">

# ⚡ Rayo Vallecano — Herramienta de Dirección Deportiva y Scouting

**Plataforma de análisis para la planificación deportiva, económica y de scouting 2026/2027**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dash](https://img.shields.io/badge/Dash-Plotly-3F4F75?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![License](https://img.shields.io/badge/Uso-Académico%20(TFM)-E30613)](#licencia)

*TFM — Máster en Big Data Deportivo · Universidad Europea · 2026*

</div>

---

## ¿Qué es?

Aplicación web de apoyo a la decisión para la dirección deportiva del **Rayo Vallecano**. Centraliza en un único dashboard el análisis de plantilla, el scouting de fichajes y la estrategia económica de la temporada, usando datos reales de OPTA y Transfermarkt.

**9 módulos**: Inicio · Plantilla · Scouting · Perfil de jugador · Comparador · Decisiones · Entrenadores · Finanzas · Criterios.

---

## Arrancar la herramienta

### Windows (recomendado)

Doble clic en `INICIAR_HERRAMIENTA.bat`. La primera vez instala las dependencias automáticamente. Después, abre **http://127.0.0.1:8050** en el navegador.

### Cualquier sistema operativo

```bash
git clone https://github.com/miguelgarciadejulian-web/TFM-rayo-scouting.git
cd TFM-rayo-scouting
pip install -r requirements.txt
python -m dashboard.app
```

No se necesita ninguna base de datos ni configuración previa: los datos viajan dentro del repositorio.

---

## Tecnologías principales

**Python 3.10+** · **Dash** + **dash-bootstrap-components** · **Plotly** · **pandas / numpy / PyArrow** · **scikit-learn** · **ReportLab** (PDF)

---

## Estructura

```
rayo_scouting_tool/
├── INICIAR_HERRAMIENTA.bat   # Arranque con doble clic (Windows)
├── requirements.txt
├── config/                   # Configuración del club (YAML/CSV)
├── data/processed/           # Datasets calculados (.parquet / .json)
├── dashboard/                # Aplicación Dash (páginas, componentes, assets)
├── src/                      # Lógica de negocio (perfilado, encaje, PDF…)
└── scripts/                  # ETL para regenerar los datasets
```

---

## Autor

**Miguel García de Julián** — miguelgarciadejulian@gmail.com
Trabajo de Fin de Máster · Universidad Europea · 2026

---

## Licencia

Proyecto académico (TFM). Los datos de OPTA y Transfermarkt pertenecen a sus respectivos propietarios. El escudo del Rayo Vallecano se usa únicamente con fines educativos.
