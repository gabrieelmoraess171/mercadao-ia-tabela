#!/bin/bash
# Iniciador macOS. Execute pelo Finder ou com bash iniciar.command.
set -e
cd -- "$(dirname -- "$0")"

falha() {
    printf '\nNão foi possível iniciar. Confira a mensagem acima.\n'
    if [ -t 0 ]; then
        read -r -p "Pressione Enter para fechar... "
    fi
    exit 1
}
trap falha ERR

if [ "$(uname -s)" != "Darwin" ]; then
    printf 'Este iniciador é para macOS. No Windows, use iniciar.bat.\n'
    exit 1
fi

mac_version=$(sw_vers -productVersion)
mac_major=${mac_version%%.*}
if [ "$mac_major" -lt 13 ]; then
    printf 'Esta versão requer macOS 13 Ventura ou posterior (Intel ou Apple Silicon).\n'
    falha
fi

if [ ! -x ".venv/bin/python" ]; then
    if ! command -v python3.12 >/dev/null 2>&1; then
        printf 'Instale Python 3.12 para macOS em https://www.python.org/downloads/macos/\n'
        falha
    fi
    python3.12 -m venv .venv
fi

if ! .venv/bin/python check_dependencies.py; then
    .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python check_dependencies.py --download-model
printf '\nPrecificador: http://127.0.0.1:8501\nMantenha esta janela aberta. Para encerrar, pressione Control+C.\n'
exec .venv/bin/python -m streamlit run app.py --server.address=127.0.0.1 --server.headless=false
