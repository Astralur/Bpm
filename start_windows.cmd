@echo off
setlocal
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
set "MKL_NUM_THREADS=1"
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Ejecuta primero install_windows.cmd con Python 3.12 instalado.
  exit /b 1
)
.venv\Scripts\python.exe -m bpm_bridge %*
exit /b %errorlevel%
