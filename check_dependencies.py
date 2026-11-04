"""Verificação local sem imprimir valores de configuração."""
import argparse
import importlib
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-model", action="store_true")
    args = parser.parse_args()
    modules = ["streamlit", "google.genai", "PIL", "pillow_heif", "rembg", "onnxruntime", "openpyxl", "dotenv", "pytesseract"]
    missing = []
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError:
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
