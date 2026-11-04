import json
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .image_processor import EXTENSIONS, MAX_FILE_BYTES, validate_size
from .models import Batch


def natural_key(path: Path):
    return [int(s) if s.isdigit() else s.casefold() for s in re.split(r"(\d+)", path.name)]


def list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ValueError("Selecione uma pasta local existente.")
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS), key=natural_key)


def safe_name(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text))
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", text).strip(" .")[:90].rstrip(" .")
    if not text:
        text = "REVISAO"
    if text.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]}:
        text = "_" + text
    return text


def create_batch(destination: Path) -> Batch:
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    folder = destination / (datetime.now().strftime("PRECIFICACAO_%d-%m-%Y_%H-%M-%S_") + uuid4().hex[:6])
    folder.mkdir(exist_ok=False)
    return Batch(folder=folder)


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp = tempfile.mkstemp(prefix=".gravando-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def save_batch(batch: Batch):
    atomic_write(batch.folder / "lote.json", batch.model_dump_json(indent=2).encode("utf-8"))


def load_batch(folder: Path) -> Batch:
    root = folder.expanduser().resolve()
    batch = Batch.model_validate_json((root / "lote.json").read_text(encoding="utf-8"))
    # Apenas lotes locais desta pasta podem ser retomados; não seguir destinos externos.
    batch.folder = root
    if batch.workbook_template and (root / "BASE_PLANILHA.xlsx").is_file():
        batch.workbook_template = root / "BASE_PLANILHA.xlsx"
    for product in batch.products:
        target = (root / product.folder.name).resolve()
        if target.parent != root:
            raise ValueError("Pasta de produto inválida.")
        product.folder = target
        for index, photo in enumerate(product.photos, 1):
            if not photo.path.exists():
                original = target / "ORIGINAIS" / f"{index:04d}-{safe_name(photo.path.stem)[:48]}{photo.path.suffix.lower()}"
                if original.exists():
                    photo.path = original
    return batch


def copy_original(source: Path, folder: Path, index: int):
    folder.mkdir(parents=True, exist_ok=True)
    if source.resolve().parent == folder.resolve():
        return
    target = folder / f"{index:04d}-{safe_name(source.stem)[:48]}{source.suffix.lower()}"
    if not target.exists():
        shutil.copy2(source, target)


def store_upload(upload, folder: Path, index: int) -> Path:
    """Copia por blocos; não duplica o lote inteiro na memória do Python."""
    validate_size(upload.size)
    name = Path(upload.name.replace("\\", "/")).name
    if Path(name).suffix.lower() not in EXTENSIONS:
        raise ValueError("Extensão não aceita.")
    target = folder / f"{index:05d}-{safe_name(Path(name).stem)}{Path(name).suffix.lower()}"
    upload.seek(0)
    copied = 0
    created = False
    try:
        with target.open("xb") as stream:
            created = True
            while block := upload.read(1024 * 1024):
                copied += len(block)
                if copied > MAX_FILE_BYTES:
                    raise ValueError("Arquivo acima de 100 MB.")
                stream.write(block)
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return target
