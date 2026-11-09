from pathlib import Path
import shutil

import pytest
from PIL import Image

from services.file_manager import list_images, load_batch, save_batch
from services.gemini_service import AIUnavailableError
from services.models import Batch, Classification, Identity, Photo, PhotoKind, Product
from services.pipeline import Options, checkpoint, prepare_batch, process_batch
from services.sku_detector import SkuDetector, from_ocr


class Processor:
    def process(self, *args, **kwargs):
        return b"fixture-jpeg", []


def prepared(photo, tmp_path):
    paths = [photo("label.png"), photo("part.png")]
    overrides = {str(path): Classification(kind=PhotoKind.LABEL if index == 0 else PhotoKind.PRODUCT,
        sku="024" if index == 0 else None, confidence=1) for index, path in enumerate(paths)}
    return prepare_batch(paths, tmp_path / "out", None, overrides=overrides), paths


def test_restored_originals_survive_saving_and_moving_lot(photo, tmp_path):
    batch, paths = prepared(photo, tmp_path)
    batch.products[0].identity = Identity(name="Alternador", confidence=1)
    process_batch(batch, processor=Processor())
    for path in paths:
        path.unlink()
    restored = load_batch(batch.folder)
    assert all(p.path.is_file() for p in restored.products[0].photos)
    save_batch(restored)
    destination = tmp_path / "movido"
    shutil.move(restored.folder, destination)
    moved = load_batch(destination)
    assert all(p.path.is_file() for p in moved.products[0].photos)
    assert all(path.is_file() for path in moved.source_paths)
    assert moved.products[0].photos[0].path.name == "0001-label.png"


def test_windows_manifest_opens_on_posix_and_recovers_originals(tmp_path):
    root = tmp_path / "lote"
    folder = root / "SKU-024-ALTERNADOR-0001"
    originals = folder / "ORIGINAIS"
    originals.mkdir(parents=True)
    actual = originals / "0001-label.png"
    actual.write_bytes(b"fixture")
    windows_folder = Path(r"C:\Users\Gabriel\resultados\lote\SKU-024-ALTERNADOR-0001")
    windows_original = Path(str(windows_folder) + r"\ORIGINAIS\0001-label.png")
    batch = Batch(folder=Path(r"C:\Users\Gabriel\resultados\lote"),
        products=[Product(id="0001", sku="024", folder=windows_folder, photos=[Photo(path=windows_original)])],
        source_paths=[windows_original])
    (root / "lote.json").write_text(batch.model_dump_json())
    loaded = load_batch(root)
    assert loaded.products[0].folder == folder
    assert loaded.products[0].photos[0].path == actual
    assert loaded.source_paths == [actual]


def test_external_windows_source_name_recovers_from_saved_original(tmp_path):
    root = tmp_path / "lote"
    folder = root / "SKU-024"
    originals = folder / "ORIGINAIS"
    originals.mkdir(parents=True)
    actual = originals / "0001-foto.png"
    actual.write_bytes(b"fixture")
    photo = Photo(path=Path(r"C:\Users\Gabriel\Pictures\foto.png"))
    batch = Batch(folder=root, products=[Product(id="0001", sku="024", folder=Path(r"C:\out\SKU-024"), photos=[photo])])
    save_batch(batch)
    loaded = load_batch(root)
    assert loaded.products[0].photos[0].path == actual


def test_relative_windows_source_recovers_on_posix_and_keeps_manual_choices(tmp_path):
    root = tmp_path / "lote"
    folder = root / "SKU-024"
    originals = folder / "ORIGINAIS"
    originals.mkdir(parents=True)
    actual = originals / "0001-foto.png"
    actual.write_bytes(b"fixture")
    source = Path(r"fotos\foto.png")
    manual = Classification(kind=PhotoKind.PRODUCT, confidence=1)
    batch = Batch(folder=root, products=[Product(id="0001", sku="024", folder=Path(r"C:\out\SKU-024"), photos=[Photo(path=source)])],
        source_paths=[source], source_overrides={str(source): manual}, source_preserve=[str(source)], source_merge_labels=[str(source)])
    save_batch(batch)
    loaded = load_batch(root)
    assert loaded.products[0].photos[0].path == actual
    assert loaded.source_paths == [actual]
    assert loaded.source_overrides[str(actual)] == manual
    assert loaded.source_preserve == [str(actual)]
    assert loaded.source_merge_labels == [str(actual)]


def test_moved_lot_uses_its_snapshot_instead_of_replaced_external_photo(photo, tmp_path):
    batch, paths = prepared(photo, tmp_path)
    process_batch(batch, processor=Processor())
    original = batch.products[0].folder / "ORIGINAIS" / "0001-label.png"
    expected = original.read_bytes()
    paths[0].write_bytes(b"different file occupying the old path")
    destination = tmp_path / "movido"
    shutil.move(batch.folder, destination)
    loaded = load_batch(destination)
    actual = loaded.products[0].photos[0].path
    assert actual.parent.name == "ORIGINAIS"
    assert actual.read_bytes() == expected


def test_preflight_cannot_override_a_readable_ocr_sku(photo, monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *a, **k: "SKU: 024")
    calls = []
    class AI:
        def classify(self, path):
            calls.append(path)
            return Classification(kind=PhotoKind.UNKNOWN, confidence=0.9)
    path = photo()
    detector = SkuDetector(AI())
    detector.validate_connection([path])
    result = detector.classify(path)
    assert result.kind == PhotoKind.LABEL and result.sku == "024"
    assert calls == [path]
    assert not detector._checked


@pytest.mark.parametrize("text,expected", [("SKU: 4694/4695", "4694/4695"),
    ("SKU\n024", "024"), ("SKU:\n024", "024"), ("SKU\n", None),
    ("SKU\nA024", "A024"), ("SKU\nProduto", None),
    ("SKU: " + "1" * 41, None), ("SKU: 024Ç", None), ("SKUPRODUTO", None)])
def test_ocr_never_silently_truncates_a_code(text, expected):
    result = from_ocr(text)
    assert result.sku == expected


def test_full_input_sequence_survives_a_mid_scan_api_failure(photo, tmp_path):
    paths = [photo(f"{index}.png") for index in range(4)]
    class Detector:
        def classify(self, path):
            if path == paths[1]:
                raise AIUnavailableError("Gemini indisponível (503)", 503)
            return Classification(kind=PhotoKind.LABEL, sku="024", confidence=1)
    with pytest.raises(AIUnavailableError) as error:
        prepare_batch(paths, tmp_path / "out", Detector())
    loaded = load_batch(error.value.batch.folder)
    assert loaded.processed == 1 and loaded.total == 4
    assert loaded.source_paths == paths


def test_pending_manual_choices_survive_a_mid_scan_failure(photo, tmp_path):
    paths = [photo(f"{index}.png") for index in range(4)]
    class Detector:
        def classify(self, path):
            if path == paths[1]:
                raise AIUnavailableError("Gemini indisponível (503)", 503)
            return Classification(kind=PhotoKind.LABEL, sku="024", confidence=1)
    overrides = {str(paths[2]): Classification(kind=PhotoKind.LABEL, sku="025", confidence=1,
        evidence="Classificação conferida manualmente.")}
    with pytest.raises(AIUnavailableError) as error:
        prepare_batch(paths, tmp_path / "out", Detector(), overrides=overrides,
                      preserve={str(paths[2])}, merge_labels={str(paths[3])})
    loaded = load_batch(error.value.batch.folder)
    assert loaded.source_overrides[str(paths[2])].sku == "025"
    assert loaded.source_preserve == [str(paths[2])]
    assert loaded.source_merge_labels == [str(paths[3])]


def test_successful_resume_clears_global_error_and_old_failure_issue(photo, tmp_path):
    batch, _ = prepared(photo, tmp_path)
    class Failed:
        usage = {}
        def identify(self, paths):
            raise AIUnavailableError("Gemini indisponível (503)", 503)
    with pytest.raises(AIUnavailableError):
        process_batch(batch, ai=Failed(), processor=Processor())
    class Working:
        usage = {}
        def identify(self, paths):
            return Identity(name="Alternador", confidence=1)
    process_batch(batch, ai=Working(), processor=Processor())
    restored = load_batch(batch.folder)
    assert restored.error is None
    assert restored.products[0].identity.name == "ALTERNADOR"
    assert restored.products[0].status == "Concluído"
    assert "Gemini indisponível (503)" not in restored.products[0].issues


def test_image_resume_does_not_clear_an_unfinished_scan_error(photo, tmp_path):
    batch, _ = prepared(photo, tmp_path)
    batch.total += 1
    batch.error = "Classificação incompleta"
    process_batch(batch, processor=Processor())
    assert load_batch(batch.folder).error == "Classificação incompleta"


def test_image_resume_without_ai_does_not_hide_an_unresolved_ai_failure(photo, tmp_path):
    batch, _ = prepared(photo, tmp_path)
    class Failed:
        usage = {}
        def identify(self, paths):
            raise AIUnavailableError("Gemini indisponível (503)", 503)
    with pytest.raises(AIUnavailableError):
        process_batch(batch, ai=Failed(), processor=Processor())
    process_batch(batch, processor=Processor())
    restored = load_batch(batch.folder)
    assert restored.error == "Gemini indisponível (503)"
    assert restored.products[0].identity.name == "Peça não identificada"
    assert restored.products[0].status == "Revisão necessária"


def test_manual_identity_review_resolves_previous_ai_failure_without_new_api_call(photo, tmp_path):
    batch, _ = prepared(photo, tmp_path)
    batch.error = "Gemini indisponível (503)"
    batch.issues = [batch.error]
    batch.products[0].issues = [batch.error]
    batch.products[0].identity = Identity(name="Alternador", confidence=0)
    batch.products[0].identity_reviewed = True
    process_batch(batch, processor=Processor())
    restored = load_batch(batch.folder)
    assert restored.error is None
    assert "Gemini indisponível (503)" not in restored.issues
    assert restored.products[0].status == "Concluído"


def test_checkpoint_persists_exporter_changes(monkeypatch, tmp_path):
    import services.pipeline as pipeline
    root = tmp_path / "lote"
    root.mkdir()
    batch = Batch(folder=root, products=[Product(id="1", folder=root)])
    def exporter(current):
        current.products[0].excel_row = 7
        current.products[0].final_override = False
    batch.products[0].final_override = True
    monkeypatch.setattr(pipeline, "export_excel", exporter)
    checkpoint(batch)
    restored = load_batch(root)
    assert restored.products[0].excel_row == 7
    assert not restored.products[0].final_override


def test_home_shortcut_is_expanded_before_listing_images(monkeypatch, tmp_path):
    path = tmp_path / "foto.png"
    Image.new("RGB", (10, 10)).save(path)
    original_expand = Path.expanduser
    monkeypatch.setattr(Path, "expanduser", lambda value: tmp_path if str(value) == "~/Pictures" else original_expand(value))
    assert list_images(Path("~/Pictures")) == [path]


def test_source_sequence_follows_renamed_internal_originals(photo, tmp_path):
    batch, paths = prepared(photo, tmp_path)
    process_batch(batch, processor=Processor())
    for path in paths:
        path.unlink()
    loaded = load_batch(batch.folder)
    loaded.source_overrides[str(loaded.source_paths[1])] = Classification(kind=PhotoKind.PRODUCT, confidence=1)
    loaded.source_preserve = [str(loaded.source_paths[1])]
    loaded.source_merge_labels = [str(loaded.source_paths[0])]
    loaded.products[0].identity = Identity(name="Alternador", confidence=1)
    process_batch(loaded, processor=Processor())
    assert all(path.is_file() for path in loaded.source_paths)
    assert set(loaded.source_overrides).issuperset({str(loaded.source_paths[1])})
    assert loaded.source_preserve == [str(loaded.source_paths[1])]
    assert loaded.source_merge_labels == [str(loaded.source_paths[0])]


def test_confirmed_identity_does_not_get_a_false_low_confidence_warning(photo, tmp_path):
    batch, _ = prepared(photo, tmp_path)
    batch.products[0].identity = Identity(name="Alternador", confidence=0)
    batch.products[0].identity_reviewed = True
    process_batch(batch, processor=Processor())
    assert not any("Identificação incerta" in issue for issue in batch.products[0].issues)
