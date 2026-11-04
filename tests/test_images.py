import io
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pillow_heif import from_pillow

from services.file_manager import store_upload
from services.image_processor import MAX_FILE_BYTES, ImageProcessor, analysis_bytes, open_image, validate_size, white_square


@pytest.mark.parametrize("suffix", ["jpg", "jpeg", "png", "heic", "heif"])
def test_decode_all_formats(tmp_path, suffix):
    image = Image.new("RGB", (120, 80), "red")
    path = tmp_path / ("imagem." + suffix)
    if suffix in ("heic", "heif"):
        from_pillow(image).save(path, quality=90)
    else:
        image.save(path)
    with open_image(path) as decoded:
        assert decoded.size == (120, 80)
        assert decoded.getpixel((20, 20))[0] > 240
    optimized = Image.open(io.BytesIO(analysis_bytes(path, 60)))
    assert optimized.size == (60, 40)


@pytest.mark.parametrize("suffix", ["jpg", "jpeg", "png", "heic", "heif"])
def test_upload_decodes_real_content(tmp_path, suffix):
    buffer = io.BytesIO()
    image = Image.new("RGB", (90, 60), "blue")
    if suffix in ("heic", "heif"):
        from_pillow(image).save(buffer)
    else:
        image.save(buffer, "JPEG" if suffix != "png" else "PNG")
    buffer.name = "imagem." + suffix
    buffer.size = buffer.getbuffer().nbytes
    saved = store_upload(buffer, tmp_path, 1)
    assert open_image(saved).size == (90, 60)


def test_limit_individual_not_batch():
    for _ in range(500):
        validate_size(MAX_FILE_BYTES)
    with pytest.raises(ValueError):
        validate_size(MAX_FILE_BYTES+1)
    with pytest.raises(ValueError):
        validate_size(0)


def test_upload_rejects_size_and_does_not_overwrite(tmp_path):
    data = io.BytesIO(b"abc")
    data.name, data.size = "test.png", MAX_FILE_BYTES+1
    with pytest.raises(ValueError):
        store_upload(data, tmp_path, 1)
    data.size = 3
    path = store_upload(data, tmp_path, 1)
    with pytest.raises(FileExistsError):
        store_upload(data, tmp_path, 1)
    assert path.read_bytes() == b"abc"


def test_corrupt_and_disguised_files(tmp_path):
    file = tmp_path / "fake.png"
    file.write_bytes(b"not an image")
    with pytest.raises(Exception):
        open_image(file)
    Image.new("RGB", (10, 10)).save(file, "GIF")
    with pytest.raises(ValueError, match="conteúdo"):
        open_image(file)


def test_exif_orientation_and_metadata_removed(tmp_path):
    file = tmp_path / "orientation.jpg"
    image = Image.new("RGB", (80, 40), "red")
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "dados privados"
    image.save(file, exif=exif)
    with open_image(file) as decoded:
        assert decoded.size == (40, 80)
        output = Image.open(io.BytesIO(white_square(decoded)))
        assert not output.getexif()


def test_white_margin_upscale_aspect_ratio_and_size():
    image = Image.new("RGBA", (100, 100))
    ImageDraw.Draw(image).rectangle((40, 45, 59, 54), fill=(20, 30, 40, 255))
    output = Image.open(io.BytesIO(white_square(image)))
    assert output.mode == "RGB" and output.size == (1200, 1200)
    for border in [(0, 0, 1200, 36), (0, 1164, 1200, 1200), (0, 0, 36, 1200), (1164, 0, 1200, 1200)]:
        assert output.crop(border).getextrema() == ((255, 255), (255, 255), (255, 255))
    mask = output.convert("L").point(lambda value: 255 if value < 100 else 0)
    bounds = mask.getbbox()
    assert bounds[2]-bounds[0] >= 1100  # objeto pequeno ampliado
    assert abs((bounds[2]-bounds[0])/(bounds[3]-bounds[1]) - 2) < 0.03
    assert abs((bounds[0]+bounds[2])/2 - 600) <= 1


def test_empty_mask_rejected():
    with pytest.raises(ValueError, match="objeto"):
        white_square(Image.new("RGBA", (100, 100)))


def test_background_removed_using_mask_without_repainting(photo, monkeypatch):
    import rembg
    processor = ImageProcessor()
    processor._session = object()
    def remove(image, **kwargs):
        output = image.copy()
        alpha = Image.new("L", image.size)
        ImageDraw.Draw(alpha).rectangle((30, 30, 170, 70), fill=255)
        output.putalpha(alpha)
        return output
    monkeypatch.setattr(rembg, "remove", remove)
    data, warnings = processor.process(photo())
    output = Image.open(io.BytesIO(data))
    assert output.getpixel((600, 600))[0] > 240
    assert output.getpixel((0, 0)) == (255, 255, 255)
    assert not warnings


def test_preserve_original_does_not_call_rembg(photo, monkeypatch):
    import rembg
    monkeypatch.setattr(rembg, "remove", lambda *a, **kw: pytest.fail("Não deve remover o fundo"))
    data, warnings = ImageProcessor().process(photo(), preserve_original=True)
    assert Image.open(io.BytesIO(data)).size == (1200, 1200)
    assert "preservado" in warnings[0]


@pytest.mark.skipif(not os.getenv("RUN_MODEL_TEST"), reason="Ative RUN_MODEL_TEST=1 para o modelo ONNX real")
def test_real_onnx_background_removal():
    fixture = Path(os.environ["MODEL_TEST_IMAGE"])
    data, _ = ImageProcessor().process(fixture)
    output = Image.open(io.BytesIO(data))
    assert output.size == (1200, 1200)
    assert output.crop((0, 0, 36, 1200)).getextrema() == ((255, 255),)*3
    assert output.convert("L").getextrema()[0] < 240
