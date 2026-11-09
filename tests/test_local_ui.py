import builtins
from types import SimpleNamespace

import pytest

from services import local_ui


@pytest.mark.parametrize("picker,expected", [
    (local_ui.choose_folder, "choose folder"),
    (local_ui.choose_workbook, "choose file"),
])
def test_mac_dialogs_run_outside_streamlit_without_importing_tk(monkeypatch, picker, expected):
    monkeypatch.setattr(local_ui.sys, "platform", "darwin")
    real_import = builtins.__import__
    def no_tk(name, *args, **kwargs):
        assert not name.startswith("tkinter"), "Não carregar Tk/AppKit na thread do Streamlit"
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_tk)
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='/Users/Gabriel/Fotos com espaço/\n', stderr="")
    monkeypatch.setattr(local_ui.subprocess, "run", run)
    assert picker() == '/Users/Gabriel/Fotos com espaço/'
    args, kwargs = calls[0]
    assert args[:2] == ["/usr/bin/osascript", "-e"]
    assert expected in args[2] and "POSIX path" in args[2]
    assert not kwargs.get("shell")
    if expected == "choose file":
        assert 'of type {"xlsx"}' in args[2]


@pytest.mark.parametrize("picker", [local_ui.choose_folder, local_ui.choose_workbook])
def test_mac_cancel_is_not_an_error(monkeypatch, picker):
    monkeypatch.setattr(local_ui.sys, "platform", "darwin")
    monkeypatch.setattr(local_ui.subprocess, "run", lambda *a, **k:
        SimpleNamespace(returncode=1, stdout="", stderr="execution error: User canceled. (-128)"))
    assert picker() == ""


def test_mac_failure_can_fall_back_to_manual_path(monkeypatch):
    monkeypatch.setattr(local_ui.sys, "platform", "darwin")
    monkeypatch.setattr(local_ui.subprocess, "run", lambda *a, **k:
        SimpleNamespace(returncode=1, stdout="", stderr="Erro de sistema"))
    with pytest.raises(RuntimeError, match="Digite o caminho"):
        local_ui.choose_folder()


def test_windows_still_uses_tk_and_destroys_window(monkeypatch):
    import sys
    monkeypatch.setattr(local_ui.sys, "platform", "win32")
    events = []
    root = SimpleNamespace(withdraw=lambda: None, attributes=lambda *a: None,
                           destroy=lambda: events.append("destroy"))
    dialog = SimpleNamespace(askdirectory=lambda **k: 'C:/Fotos', askopenfilename=lambda **k: 'C:/Pecas.xlsx')
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(Tk=lambda: root, filedialog=dialog))
    assert local_ui.choose_folder() == 'C:/Fotos'
    assert local_ui.choose_workbook() == 'C:/Pecas.xlsx'
    assert events == ["destroy", "destroy"]


def test_mac_launcher_reuses_environment_and_starts_in_project_folder(tmp_path, monkeypatch):
    from pathlib import Path
    import os
    import shutil
    import subprocess
    root = tmp_path / "Pasta com espaço"
    root.mkdir()
    launcher = root / "iniciar.command"
    shutil.copy2(Path(__file__).resolve().parents[1] / "iniciar.command", launcher)
    commands = tmp_path / "comandos"
    commands.mkdir()
    uname = commands / "uname"
    uname.write_text('#!/bin/sh\nprintf "Darwin\\n"\n')
    uname.chmod(0o755)
    sw_vers = commands / "sw_vers"
    sw_vers.write_text('#!/bin/sh\nprintf "13.7.6\\n"\n')
    sw_vers.chmod(0o755)
    interpreter = root / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text('#!/bin/sh\nprintf "%s:%s\\n" "$PWD" "$*" >> "$PRECIFICADOR_TEST_LOG"\n')
    interpreter.chmod(0o755)
    log = tmp_path / "launch.log"
    monkeypatch.setenv("PATH", str(commands) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PRECIFICADOR_TEST_LOG", str(log))
    result = subprocess.run(["bash", str(launcher)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    lines = log.read_text().splitlines()
    assert lines == [f"{root}:check_dependencies.py", f"{root}:check_dependencies.py --download-model",
                     f"{root}:-m streamlit run app.py --server.address=127.0.0.1 --server.headless=false"]
