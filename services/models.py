from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


class PhotoKind(str, Enum):
    LABEL = "Etiqueta SKU"
    PRODUCT = "Produto"
    MEASUREMENT = "Medida"
    WEIGHT = "Peso"
    DETAIL = "Código/Detalhe"
    UNKNOWN = "Não identificada"


class Classification(BaseModel):
    kind: PhotoKind = PhotoKind.UNKNOWN
    sku: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: str = ""


class Identity(BaseModel):
    name: str = "Peça não identificada"
    part_type: str | None = None
    manufacturer: str | None = None
    vehicle_brand: str | None = None
    vehicle_model: str | None = None
    version: str | None = None
    years: str | None = None
    side: str | None = None
    position: str | None = None
    oem: str | None = None
    part_number: str | None = None
    inscriptions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)

    def query(self) -> str:
        return " ".join(dict.fromkeys(str(v) for v in [self.name, self.vehicle_brand,
            self.vehicle_model, self.version, self.years, self.side, self.position,
            self.oem, self.part_number] if v))[:500]


class Compatibility(BaseModel):
    compatible: bool = False
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: str = ""


class Reference(BaseModel):
    title: str
    price: Decimal | None = Field(default=None, gt=0)
    url: str
    consulted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    condition: str = "desconhecida"
    status: str = "Revisão necessária"
    verified: bool = False
    compatible: bool = False
    source: str = "manual"
    reason: str = ""


class Photo(BaseModel):
    path: Path
    classification: Classification = Field(default_factory=Classification)
    error: str | None = None
    preserve_original: bool = False
    merge_with_previous: bool = False
    review_reason: str | None = None
    output: str | None = None


class Product(BaseModel):
    id: str
    sku: str | None = None
    folder: Path
    photos: list[Photo] = Field(default_factory=list)
    identity: Identity = Field(default_factory=Identity)
    identity_reviewed: bool = False
    references: list[Reference] = Field(default_factory=list)
    final: Decimal | None = Field(default=None, ge=0)
    final_override: bool = False
    references_edited: bool = False
    excel_row: int | None = None
    excel_key: str = Field(default_factory=lambda: uuid4().hex)
    status: str = "Aguardando"
    issues: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class Batch(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    folder: Path
    products: list[Product] = Field(default_factory=list)
    processed: int = 0
    total: int = 0
    searches: int = 0
    issues: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    ai_model: str | None = None
    error: str | None = None
    excel_layout: str = "standard"
    workbook_template: Path | None = None
    source_paths: list[Path] = Field(default_factory=list)
    source_overrides: dict[str, Classification] = Field(default_factory=dict)
    source_preserve: list[str] = Field(default_factory=list)
    source_merge_labels: list[str] = Field(default_factory=list)
