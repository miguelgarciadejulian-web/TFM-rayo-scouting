@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo ============================================================
echo   Rayo Vallecano - Herramienta de Scouting 2026/27
echo ============================================================
echo.

REM === 1. Buscar un Python valido (evitando el alias de Microsoft Store) ======
set "PYEXE="

REM 1a) Rutas tipicas de Anaconda / Miniconda
for %%P in (
  "%USERPROFILE%\anaconda3\python.exe"
  "%USERPROFILE%\Anaconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "%USERPROFILE%\Miniconda3\python.exe"
  "%LOCALAPPDATA%\anaconda3\python.exe"
  "%LOCALAPPDATA%\Continuum\anaconda3\python.exe"
  "C:\ProgramData\Anaconda3\python.exe"
  "C:\ProgramData\anaconda3\python.exe"
  "C:\ProgramData\Miniconda3\python.exe"
) do (
  if not defined PYEXE if exist "%%~P" set "PYEXE=%%~P"
)

REM 1b) Lanzador 'py' del instalador oficial de Python
if not defined PYEXE (
  where py >nul 2>&1 && set "PYEXE=py"
)

REM 1c) 'python' en el PATH (ultimo recurso)
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
)

if not defined PYEXE (
  echo [ERROR] No se ha encontrado Python en el sistema.
  echo.
  echo   Opcion A: instala Python 3.10+ desde https://www.python.org/downloads/
  echo             marcando la casilla "Add Python to PATH".
  echo   Opcion B: si usas Anaconda, abre "Anaconda Prompt", entra en esta carpeta
  echo             y ejecuta:  python -m dashboard.app
  echo.
  pause
  exit /b 1
)

echo Usando Python: !PYEXE!
echo.

REM === 2. Instalar dependencias (solo la primera vez) =========================
if exist ".deps_ok" (
  echo Dependencias ya instaladas. ^(Borra el archivo .deps_ok para reinstalar^)
) else (
  echo Instalando dependencias por primera vez ^(puede tardar unos minutos^)...
  "!PYEXE!" -m pip install --upgrade pip
  "!PYEXE!" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias. Revisa tu conexion e intentalo de nuevo.
    pause
    exit /b 1
  )
  echo ok> ".deps_ok"
)
echo.

REM === 3. Arrancar el dashboard ===============================================
echo ============================================================
echo   Abre esta direccion en tu navegador:
echo        http://127.0.0.1:8050
echo   ^(espera unos segundos a que arranque; para detenerla
echo    cierra esta ventana o pulsa Ctrl+C^)
echo ============================================================
echo.
"!PYEXE!" -m dashboard.app

echo.
echo La herramienta se ha detenido.
pause
