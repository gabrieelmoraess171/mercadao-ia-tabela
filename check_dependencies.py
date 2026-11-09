"""Verificação local sem imprimir valores de configuração."""
import argparse
import importlib
from importlib import metadata
from pathlib import Path
import shutil


def incompatible_requirements(path=None, *, environment=None, installed_version=None):
    """Verifica também versões; importar uma biblioteca antiga não basta."""
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return ["packaging (verificador de versões ausente)"]
    installed_version = installed_version or metadata.version
    path = path or Path(__file__).resolve().with_name("requirements.txt")
    incompatible = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate(environment=environment):
            continue
        try:
            installed = installed_version(requirement.name)
        except metadata.PackageNotFoundError:
            incompatible.append(f"{requirement.name} (ausente)")
            continue
        if not requirement.specifier.contains(installed, prereleases=True):
            incompatible.append(f"{requirement.name}: instalada {installed}; necessária {requirement.specifier}")
    return incompatible


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-model", action="store_true")
    args = parser.parse_args()
    incompatible = incompatible_requirements()
    if incompatible:
        print("Dependências a instalar ou atualizar:", "; ".join(incompatible))
        return 1
    modules = ["streamlit", "google.genai", "PIL", "pillow_heif", "rembg", "onnxruntime", "openpyxl", "dotenv", "pytesseract"]
    missing = []
    for module in modules:
        try:
            importlib.import_module(module)
        except (ImportError, OSError):
            missing.append(module)
    if missing:
        print("Dependências ausentes:", ", ".join(missing))
        return 1
    print("Dependências Python: OK")
    print("OCR Tesseract:", "disponível" if shutil.which("tesseract") else "opcional: instale ou configure TESSERACT_CMD; Gemini faz a alternativa")
    if args.download_model:
        from rembg import new_session
        new_session("u2netp", providers=["CPUExecutionProvider"])
        print("Modelo local de remoção de fundo: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
