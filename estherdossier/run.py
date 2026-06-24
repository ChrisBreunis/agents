"""End-to-end lokale pijplijn: inlezen → feitenrapport → inhoudelijke duiding.

Draai:  python run.py

Stap 1 (inlezen) en 2 (feitenrapport) draaien altijd.
Stap 3 (duiding door Claude) draait alleen als ANTHROPIC_API_KEY is gezet.
"""
from __future__ import annotations

import os

import local_ingest
import report
from paths import load_paths


def main() -> None:
    print("=== Stap 1/3 — documenten inlezen en extraheren ===")
    local_ingest.main()

    print("\n=== Stap 2/3 — feitenrapport + tijdlijn ===")
    paths = load_paths()
    report_path = report.build_report(paths)
    print(f"✓ Feitenrapport: {report_path}")

    print("\n=== Stap 3/3 — inhoudelijke duiding (Claude) ===")
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⏭  Overgeslagen: ANTHROPIC_API_KEY niet gezet.")
        print("   Zet je sleutel (export ANTHROPIC_API_KEY=sk-ant-...) en draai: python analyze.py")
        return
    import analyze
    analyze.main()


if __name__ == "__main__":
    main()
