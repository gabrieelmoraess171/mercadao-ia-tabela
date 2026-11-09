import json
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from .image_processor import EXTENSIONS, MAX_FILE_BYTES, validate_size
from .models import Batch


def natural_key(path: Path):
    return [int(s) if s.isdigit() else s.casefold() for s in re.split(r"(\d+)", path.name)]


def list_images(folder: Path) -> list[Path]:
    folder = folder.expanduser()
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
    moved_batch = _saved_path(batch.folder) != _saved_path(root)
    # Apenas lotes locais desta pasta podem ser retomados; não seguir destinos externos.
    batch.folder = root
    if batch.workbook_template and (root / "BASE_PLANILHA.xlsx").is_file():
        batch.workbook_template = root / "BASE_PLANILHA.xlsx"
    relocated = {}
    for product in batch.products:
        previous_folder = _saved_path(product.folder)
        target = (root / previous_folder.name).resolve()
        if target.parent != root:
            raise ValueError("Pasta de produto inválida.")
        product.folder = target
        for index, photo in enumerate(product.photos, 1):
            previous_path = photo.path
            saved = _saved_path(previous_path)
            # Um caminho já recuperado aponta para ORIGINAIS. Ao mover o lote,
            # preserve esse caminho relativo, sem duplicar o prefixo 0001-.
            try:
                relative = saved.relative_to(previous_folder)
                local = target.joinpath(*relative.parts).resolve()
                if local.is_relative_to(target) and local.is_file():
                    photo.path = local
            except ValueError:
                pass
            # Ao transferir um lote, a cópia que acompanha o grupo prevalece:
            # o computador de destino pode ter outro arquivo no antigo caminho.
            if moved_batch or not photo.path.is_file():
                original = target / "ORIGINAIS" / f"{index:04d}-{safe_name(saved.stem)[:48]}{saved.suffix.lower()}"
                if original.is_file():
                    photo.path = original
                elif saved.parent.name.upper() == "ORIGINAIS":
                    original = target / "ORIGINAIS" / saved.name
                    if original.is_file():
                        photo.path = original
            relocated[str(previous_path)] = photo.path
    relocate_sources(batch, relocated)
    return batch


def relocate_sources(batch: Batch, moved: dict):
    """Mantém sequência e escolhas manuais ligadas aos arquivos recuperados."""
    batch.source_paths = [moved.get(str(path), path) for path in batch.source_paths]
    batch.source_overrides = {str(moved.get(path, path)): value for path, value in batch.source_overrides.items()}
    batch.source_preserve = [str(moved.get(path, path)) for path in batch.source_preserve]
    batch.source_merge_labels = [str(moved.get(path, path)) for path in batch.source_merge_labels]


def _saved_path(value):
    """Interpreta o caminho no sistema em que o lote foi salvo."""
    text = str(value)
    if re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("\\\\") or ("\\" in text and not text.startswith("/")):
        return PureWindowsPath(text)
    return PurePosixPath(text)


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
