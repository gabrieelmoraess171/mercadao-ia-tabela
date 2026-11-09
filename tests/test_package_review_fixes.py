from pathlib import Path
from zipfile import ZipFile

from build_packages import build_packages, version_of


def test_packages_match_current_code_without_stock_or_installed_environment(tmp_path):
    root = Path(__file__).resolve().parents[1]
    version = version_of(root)
    packages = build_packages(root, tmp_path)
    for path in packages:
        with ZipFile(path) as archive:
            assert archive.testzip() is None
            assert f"-{version}.zip" in path.name
            for file in ["app.py", "requirements.txt", "check_dependencies.py", *[str(p.relative_to(root)) for p in (root / "services").glob("*.py")]]:
                assert archive.read(file) == (root / file).read_bytes()
            names = archive.namelist()
            assert not any(n == ".env" or ".venv" in n or n.endswith((".xlsx", ".jpg", ".heic")) for n in names)
            if "-mac-" in path.name:
                assert "iniciar.command" in names and "iniciar.bat" not in names
                assert archive.getinfo("iniciar.command").external_attr >> 16 & 0o111
            else:
                assert "iniciar.bat" in names and "iniciar.command" not in names
