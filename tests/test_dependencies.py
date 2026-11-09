from importlib import metadata
from pathlib import Path
import subprocess

import check_dependencies


def test_macos_requirements_have_compatible_intel_and_arm_pins():
    from packaging.requirements import Requirement
    requirements = [Requirement(line) for line in Path("requirements.txt").read_text().splitlines()
                    if line.strip() and not line.startswith("#")]
    for architecture in ("x86_64", "arm64"):
        environment = {"sys_platform": "darwin", "platform_machine": architecture}
        applicable = {r.name: str(r.specifier) for r in requirements
                      if not r.marker or r.marker.evaluate(environment)}
        assert applicable["onnxruntime"] == "==1.23.2"
        assert applicable["numpy"] == "==2.3.5"
        assert applicable["numba"] == "==0.62.1"
        assert applicable["rembg"] == "==2.0.86"


def test_windows_does_not_use_mac_compatibility_pins():
    from packaging.requirements import Requirement
    requirements = [Requirement(line) for line in Path("requirements.txt").read_text().splitlines()
                    if line.strip() and not line.startswith("#")]
    applicable = {r.name: str(r.specifier) for r in requirements
                  if not r.marker or r.marker.evaluate({"sys_platform": "win32"})}
    assert applicable["onnxruntime"] == "==1.31.1"
    assert "numpy" not in applicable and "numba" not in applicable


def test_check_detects_installed_but_wrong_version(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text('onnxruntime==1.23.2; sys_platform == "darwin"\nonnxruntime==1.31.1; sys_platform != "darwin"\n')
    mismatches = check_dependencies.incompatible_requirements(requirements,
        environment={"sys_platform": "darwin"}, installed_version=lambda name: "1.31.1")
    assert len(mismatches) == 1 and "==1.23.2" in mismatches[0]
    assert not check_dependencies.incompatible_requirements(requirements,
        environment={"sys_platform": "win32"}, installed_version=lambda name: "1.31.1")


def test_check_detects_missing_distribution(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("missing-package==1.0\n")
    def missing(name):
        raise metadata.PackageNotFoundError(name)
    assert check_dependencies.incompatible_requirements(requirements, installed_version=missing) == ["missing-package (ausente)"]


def test_mac_launcher_rejects_unsupported_os_before_installing(tmp_path, monkeypatch):
    import os
    launcher = Path(__file__).resolve().parents[1] / "iniciar.command"
    commands = tmp_path / "commands"
    commands.mkdir()
    for command, value in (("uname", "Darwin"), ("sw_vers", "12.7.6")):
        executable = commands / command
        executable.write_text(f'#!/bin/sh\nprintf "{value}\\n"\n')
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(commands) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(["bash", str(launcher)], cwd=tmp_path, text=True, capture_output=True, stdin=subprocess.DEVNULL)
    assert result.returncode == 1
    assert "macOS 13 Ventura" in result.stdout
