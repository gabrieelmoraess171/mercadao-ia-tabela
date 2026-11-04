from pathlib import Path
import sys

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def photo(tmp_path):
    def make(name="foto.png", size=(200, 100)):
        path = tmp_path / name
        image = Image.new("RGB", size, "white")
        ImageDraw.Draw(image).rectangle((30, 30, size[0]-30, size[1]-30), fill="red")
        image.save(path)
        return path
    return make
