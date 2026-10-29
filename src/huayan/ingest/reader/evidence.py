"""读取侧的原文、原生位置和标签读数；不写入契的正式状态。"""
from hashlib import sha256
from typing import Literal

from huayan.contracts import Fragment
from huayan.contracts._base import BaseModel
from huayan.contracts.seeds import Level


class Location(BaseModel):
    page: int
    image_path: str
    bbox: tuple[int, int, int, int] | None = None


class TableCell(BaseModel):
    row: int
    column: int
    text: str


class EvidenceBlock(BaseModel):
    source_id: str
    file_sha256: str
    span: str
    text: str
    level: Level
    source: Literal["public", "internal", "external"]
    kind: Literal["paragraph", "table", "textbox"]
    section: str = ""
    group: Literal["A", "B"] | None = None
    locations: list[Location] = []
    cells: list[TableCell] = []

    def fragment(self):
        return Fragment(doc_id=self.source_id, span=self.span, text=self.text, level=self.level,
                        source=self.source, fingerprint=sha256(self.text.encode("utf-8")).hexdigest()[:12])


class Reading(BaseModel):
    span: str
    cell: tuple[int, int] | None = None
    object: str
    group: Literal["A", "B"] | None = None
    stage: str | None = None
    value: str
    unit: str
    conditions: list[str] = []
    quote: str
    status: Literal["native", "needs_reading"] = "native"
