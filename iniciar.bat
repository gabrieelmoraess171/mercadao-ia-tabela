@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo Instale Python 3.12 de python.org, com pip e Tcl/Tk.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" check_dependencies.py
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Falha na instalacao. Confira internet e Python 64 bits.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" check_dependencies.py --download-model
if errorlevel 1 (
    echo Nao foi possivel preparar o removedor de fundo. Confira a conexao.
    pause
    exit /b 1
)
start "" "http://127.0.0.1:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.headless=true
if errorlevel 1 pause
