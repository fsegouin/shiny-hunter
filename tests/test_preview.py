"""Integration test for the shiny preview pipeline.

Requires real ROM files — skipped unless roms/ directory is populated.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROMS_DIR = Path("roms")

needs_rom = pytest.mark.skipif(
    not ROMS_DIR.exists() or not any(ROMS_DIR.glob("*.gb")),
    reason="requires ROM files in roms/",
)


@needs_rom
def test_preview_pipeline_produces_png(tmp_path):
    """Smoke test: run the preview pipeline and verify a PNG is produced.

    This test is a skeleton that should be filled in once ROM files,
    a Crystal ROM, template state, and macros are available.
    """
    # To run this test:
    # 1. Place a Gen 1 ROM in roms/
    # 2. Place a Crystal ROM in roms/
    # 3. Create a trace JSON, Gen 1 state, Gen 1 macro, Crystal state, Crystal macro
    # 4. Update the paths below
    pytest.skip("requires manual setup — see comment above")
