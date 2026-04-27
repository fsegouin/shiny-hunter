"""Per-attempt run traces for reproducing a found shiny."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .dv import DVs


@dataclass(frozen=True)
class Trace:
    schema: int
    rom_sha1: str
    state_sha1: str
    game: str
    region: str
    starter: str
    master_seed: int
    attempt: int
    delay: int
    species: int
    species_name: str
    dvs: dict[str, int]


def sha1_of_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha1_of_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def write(
    out_path: Path,
    *,
    rom_path: Path,
    state_bytes: bytes,
    game: str,
    region: str,
    starter: str,
    master_seed: int,
    attempt: int,
    delay: int,
    species: int,
    species_name: str,
    dvs: DVs,
) -> Trace:
    trace = Trace(
        schema=1,
        rom_sha1=sha1_of_file(rom_path),
        state_sha1=sha1_of_bytes(state_bytes),
        game=game,
        region=region,
        starter=starter,
        master_seed=master_seed,
        attempt=attempt,
        delay=delay,
        species=species,
        species_name=species_name,
        dvs=dvs.as_dict(),
    )
    out_path.write_text(json.dumps(asdict(trace), indent=2))
    return trace


def load(path: Path) -> Trace:
    raw = json.loads(Path(path).read_text())
    return Trace(**raw)
