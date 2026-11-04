"""Diálogos nativos no computador que executa o Streamlit (Windows local)."""
import os
import subprocess
import sys
from pathlib import Path


def choose_folder() -> str:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=root, title="Selecione a pasta")
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
