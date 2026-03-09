from dataclasses import dataclass
from typing import Dict


@dataclass
class Document:
    id: str
    title: str
    text: str
    source: str
    path: str
    metadata: Dict