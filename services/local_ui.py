"""Diálogos locais: AppleScript no macOS, Tkinter no Windows/Linux."""
import os
import subprocess
import sys
from pathlib import Path


def _mac_dialog(script: str) -> str:
    # AppKit/Tk não pode criar janelas na thread de execução do Streamlit.
    # osascript executa o seletor nativo em um processo separado do servidor.
    result = subprocess.run(["/usr/bin/osascript", "-e", script],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        if "(-128)" in result.stderr:  # Usuário cancelou o diálogo.
            return ""
        raise RuntimeError("Seletor do macOS indisponível. Digite o caminho do arquivo ou pasta.")
    return result.stdout.rstrip("\r\n")


def choose_folder() -> str:
    if sys.platform == "darwin":
        return _mac_dialog('return POSIX path of (choose folder with prompt "Selecione a pasta")')
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=root, title="Selecione a pasta")
    finally:
        root.destroy()


def choose_workbook() -> str:
    if sys.platform == "darwin":
        return _mac_dialog('return POSIX path of (choose file with prompt "Selecione a planilha existente" of type {"xlsx"})')
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(parent=root, title="Selecione a planilha existente", filetypes=[("Planilha Excel", "*.xlsx")])
    finally:
        root.destroy()


def open_local(path: Path):
    path = path.resolve()
    if not path.exists():
        raise ValueError("Arquivo ou pasta não encontrado.")
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
