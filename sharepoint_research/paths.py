"""Gedeelde pad- en modelconfiguratie voor de LOKALE flow.

Vraagt — anders dan config.py (die is voor de optionele SharePoint/Graph-route) —
geen SharePoint-gegevens. Alles draait lokaal op een map met documenten.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent


@dataclass
class Paths:
    input_dir: Path
    output_dir: Path
    llm_model: str

    @property
    def text_dir(self) -> Path:
        return self.output_dir / "tekst"

    @property
    def manifest_path(self) -> Path:
        return self.output_dir / "manifest.json"


def load_paths() -> Paths:
    input_dir = Path(os.getenv("INPUT_DIR", str(BASE_DIR / "input_documenten")))
    output_dir = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "output")))
    # claude-opus-4-8 = Claude's meest capabele model; overschrijfbaar via .env
    llm_model = os.getenv("LLM_MODEL", "claude-opus-4-8").strip()
    return Paths(input_dir=input_dir, output_dir=output_dir, llm_model=llm_model)
