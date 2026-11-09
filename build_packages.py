"""Gera os dois pacotes a partir de uma lista explícita de arquivos públicos."""
import argparse
import ast
from pathlib import Path
import os
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


def version_of(root: Path) -> str:
    module = ast.parse((root / "app.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "APP_VERSION" for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and re.fullmatch(r"\d+\.\d+\.\d+", value):
                return value
    raise ValueError("APP_VERSION ausente ou inválida.")


def build_packages(root: Path, output: Path) -> list[Path]:
    version = version_of(root)
    common = ["app.py", "check_dependencies.py", "requirements.txt", ".env.example", "README.md", "VALIDACAO.md",
              "COMO_ATUALIZAR.txt", ".streamlit/config.toml", "oauth-retorno/retorno.html", "oauth-retorno/README.md"]
    common += [str(path.relative_to(root)) for path in sorted((root / "services").glob("*.py"))]
    output.mkdir(parents=True, exist_ok=True)
    packages = []
    for platform, launcher, guide in [("mac", "iniciar.command", "LEIA_ME_MAC.txt"),
                                      ("windows", "iniciar.bat", "LEIA_ME_WINDOWS.txt")]:
        target = output / f"precificador-{platform}-{version}.zip"
        descriptor, temporary = tempfile.mkstemp(prefix=".pacote-", suffix=".zip", dir=output)
        os.close(descriptor)
        try:
            with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
                for name in [*common, launcher, guide]:
                    archive.write(root / name, name)
            with ZipFile(temporary) as archive:
                if archive.testzip() is not None:
                    raise ValueError("Falha de integridade do pacote.")
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        packages.append(target)
    return packages


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "downloads")
    options = parser.parse_args()
    for package in build_packages(Path(__file__).resolve().parent, options.output):
        print(package)
