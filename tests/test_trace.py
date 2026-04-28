from pathlib import Path

from shiny_hunter import trace
from shiny_hunter.dv import decode_dvs


def test_write_and_load_roundtrip(tmp_path: Path):
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"\x00" * 1024)
    state_bytes = b"\xAA" * 256
    dvs = decode_dvs(0xAA, 0xAA)  # atk=10 def=10 spd=10 spc=10  (shiny!)
    out = tmp_path / "shiny.trace.json"

    written = trace.write(
        out,
        rom_path=rom,
        state_bytes=state_bytes,
        game="red",
        region="us",
        state_path="states/red_us_bulbasaur.state",
        master_seed=12345,
        attempt=42,
        delay=173,
        species=0x99,
        species_name="bulbasaur",
        dvs=dvs,
    )
    loaded = trace.load(out)
    assert loaded == written
    assert loaded.rom_sha1 == trace.sha1_of_file(rom)
    assert loaded.state_sha1 == trace.sha1_of_bytes(state_bytes)
    assert loaded.state_path == "states/red_us_bulbasaur.state"
    assert loaded.dvs == {"atk": 10, "def": 10, "spd": 10, "spc": 10, "hp": 0}


def test_sha1_of_bytes_matches_known_value():
    assert trace.sha1_of_bytes(b"") == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    assert trace.sha1_of_bytes(b"abc") == "a9993e364706816aba3e25717850c26c9cd0d89d"
