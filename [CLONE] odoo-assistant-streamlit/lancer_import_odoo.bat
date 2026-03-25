@echo off
setlocal

cd /d "%~dp0"

REM --- Active le venv local
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [ERREUR] Aucun venv trouve dans .venv
    echo Cree-le avec: python -m venv .venv
    pause
    exit /b 1
)

REM --- Lance le nouveau wizard éclaté
python main.py

pause
endlocal
