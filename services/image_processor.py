"""Leitura sequencial e composição fotográfica, sem geração de detalhes."""
import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps, ImageCms
from pillow_heif import register_heif_opener

register_heif_opener()
MAX_FILE_BYTES = 100 * 1024 * 1024
EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
FORMATS = {"JPEG", "PNG", "HEIF", "HEIC"}
# Limite explícito contra imagens comprimidas com dimensões perigosas.
Image.MAX_IMAGE_PIXELS = 100_000_000


def validate_size(size: int) -> None:
    if size <= 0 or size > MAX_FILE_BYTES:
        raise ValueError("O arquivo deve ter conteúdo e no máximo 100 MB individualmente.")


def open_image(path: Path) -> Image.Image:
    validate_size(path.stat().st_size)
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError("Formato de arquivo não aceito.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as original:
            if original.format not in FORMATS:
                raise ValueError("O conteúdo não é JPG, PNG ou HEIC/HEIF.")
            original.load()
            oriented = ImageOps.exif_transpose(original).convert("RGBA")
            profile = original.info.get("icc_profile")
            if profile:
                try:
                    rgb = ImageCms.profileToProfile(oriented.convert("RGB"),
                        ImageCms.ImageCmsProfile(io.BytesIO(profile)), ImageCms.createProfile("sRGB"), outputMode="RGB")
                    rgb.putalpha(oriented.getchannel("A"))
                    oriented.close()
                    oriented = rgb
                except (ImageCms.PyCMSError, OSError):
                    pass
            return oriented


def analysis_bytes(path: Path, max_side: int = 2000) -> bytes:
    with open_image(path) as image:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        rgb = Image.new("RGB", image.size, "white")
        rgb.paste(image, mask=image.getchannel("A"))
        buffer = io.BytesIO()
        rgb.save(buffer, "JPEG", quality=92)
        return buffer.getvalue()


def white_square(image: Image.Image, quality: int = 92) -> bytes:
    """Recorta pelo alfa, amplia/reduz proporcionalmente e impõe 36 px de margem."""
    rgba = image.convert("RGBA")
    # Ignora ruído quase transparente na detecção; conserva o alfa no recorte.
    bounds = rgba.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if not bounds:
        raise ValueError("Remoção sem objeto visível; use a opção de preservar a original.")
    cropped = rgba.crop(bounds)
    w, h = cropped.size
    # 40 px (múltiplo de 8) evita que o DCT do JPEG contamine a borda branca
    # obrigatória de 36 px. Continua dentro da área útil máxima de 1128 px.
    scale = min(1120 / w, 1120 / h)
    size = (max(1, min(1120, round(w * scale))), max(1, min(1120, round(h * scale))))
    resized = cropped.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1200, 1200), (255, 255, 255))
    canvas.paste(resized, ((1200-size[0])//2, (1200-size[1])//2), resized.getchannel("A"))
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=quality, optimize=True, subsampling=0)
    return buffer.getvalue()


class ImageProcessor:
    def __init__(self, quality: int = 92):
        self.quality = quality
        self._session = None

    def process(self, path: Path, preserve_original: bool = False) -> tuple[bytes, list[str]]:
        with open_image(path) as image:
            if preserve_original:
                return white_square(image, self.quality), []
            from rembg import new_session, remove
            if self._session is None:
                self._session = new_session("u2netp", providers=["CPUExecutionProvider"])
            # A análise para segmentação é limitada; o recorte usa a foto original.
            sample = image.copy()
            sample.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            cutout = remove(sample, session=self._session)
            mask = cutout.getchannel("A").resize(image.size, Image.Resampling.LANCZOS)
            alpha_bounds = mask.point(lambda v: 255 if v > 10 else 0).getbbox()
            if not alpha_bounds:
                raise ValueError("O removedor apagou todo o objeto. Revise ou preserve a original.")
            histogram = mask.histogram()
            visible = sum(histogram[11:]) / (image.width * image.height)
            if visible < 0.001:
                raise ValueError("Recorte muito pequeno; revisão necessária para evitar perda da peça.")
            image.putalpha(mask)
            warnings = []
            if visible < 0.01:
                warnings.append("Área identificada pequena; confira se a peça e os detalhes importantes foram mantidos.")
            if visible > 0.98:
                warnings.append("Quase toda a foto foi mantida; confira se o fundo e itens secundários foram removidos.")
            left, top, right, bottom = alpha_bounds
            if left == 0 or top == 0 or right == image.width or bottom == image.height:
                warnings.append("O recorte encosta na borda da foto; confira se a peça ou uma etiqueta foi cortada na origem.")
            return white_square(image, self.quality), warnings
