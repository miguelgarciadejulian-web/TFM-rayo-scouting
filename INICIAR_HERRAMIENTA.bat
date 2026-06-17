@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo ============================================================
echo   Rayo Vallecano - Herramienta de Scouting 2026/27
echo ============================================================
echo.

REM ── Buscar un Python valido (evitando el alias de Microsoft Store) ─────────
set "PYEXE="

REM 1) Rutas tipicas de Anaconda / Miniconda
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

REM 2) Lanzador 'py' del instalador oficial de Python
if not defined PYEXE (
  where py >nul 2>&1 && set "PYEXE=py"
)

if not defined PYEXE (
  echo No se ha encontrado Python.
  echo Abre "Anaconda Prompt" desde el menu Inicio y ejecuta dentro de esta carpeta:
  echo     python -m dashboard.app
  echo.
  pause
  exit /b 1
)

echo Usando Python: !PYEXE!
echo.
echo Comprobando dependencias (la primera vez tarda un poco)...
"!PYEXE!" -m pip install -r requirements.txt
echo.
echo ============================================================
echo   Abre en el navegador:  http://127.0.0.1:8050
echo   (Para parar: cierra esta ventana o pulsa Ctrl+C)
echo ============================================================
echo.
"!PYEXE!" -m dashboard.app
pause
