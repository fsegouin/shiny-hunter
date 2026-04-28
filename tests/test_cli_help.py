"""Smoke tests for `--help` output: every CLI option must carry documentation.

These tests invoke the Click CLI in-process without touching PyBoy, so
they're safe to run in CI without a ROM.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from shiny_hunter.cli import main

# Per-subcommand: each option name must appear in --help, AND the help
# text for each command must be longer than just the option list (a
# proxy for "every flag has a help= string", since Click renders flags
# without help= as just the flag).
EXPECTED_OPTIONS: dict[str, set[str]] = {
    "list-games": set(),
    "bootstrap": {"--rom", "--out"},
    "verify": {"--rom", "--state", "--macro", "--game", "--region", "--window"},
    "run": {
        "--rom", "--state", "--macro", "--game", "--region",
        "--max-attempts", "--seed", "--out",
        "--headless/--window", "--continue-after-shiny",
    },
    "replay": {"--trace", "--rom", "--macro"},
    "resume": {"--rom", "--state"},
    "record": {"--rom", "--from-state", "--out", "--max-frames", "--game", "--region"},
}


@pytest.mark.parametrize("cmd", sorted(EXPECTED_OPTIONS.keys()))
def test_subcommand_help_lists_all_options(cmd: str):
    runner = CliRunner()
    result = runner.invoke(main, [cmd, "--help"])
    assert result.exit_code == 0, result.output
    for opt in EXPECTED_OPTIONS[cmd]:
        # Click renders combined flags like "--headless / --window"; allow the spaced form.
        if "/" in opt:
            a, b = opt.split("/")
            assert a in result.output and b in result.output, f"{opt!r} missing in {cmd} --help"
        else:
            assert opt in result.output, f"{opt!r} missing in {cmd} --help"


@pytest.mark.parametrize("cmd", [c for c, opts in EXPECTED_OPTIONS.items() if opts])
def test_subcommand_help_documents_each_flag(cmd: str):
    """Heuristic: every option line should have non-trivial trailing text.

    Click formats each option as "  --foo TYPE   <help text>". If help= is
    omitted, the trailing text is just the type or empty. We require >=3
    words on the help side for every recorded option.
    """
    runner = CliRunner()
    result = runner.invoke(main, [cmd, "--help"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    for opt in EXPECTED_OPTIONS[cmd]:
        # Combined flags appear as "--headless / --window"; first half is enough to find the line.
        needle = opt.split("/")[0]
        matches = [ln for ln in lines if needle in ln and ln.lstrip().startswith("-")]
        assert matches, f"could not find help line for {opt!r} in {cmd} --help"
        # Take the matched line and any continuation indented under it.
        idx = lines.index(matches[0])
        block = matches[0]
        for cont in lines[idx + 1 :]:
            if cont.startswith("  ") and not cont.lstrip().startswith("-"):
                block += " " + cont.strip()
            else:
                break
        # After the option/type, ensure some prose remains.
        # Cut off the option name + any TYPE token to leave just the help text.
        tail = block.split(needle, 1)[1].strip()
        # Tail typically starts with TYPE then help; require at least 3 words after.
        words = tail.split()
        assert len(words) >= 3, f"{opt!r} in {cmd} --help looks undocumented: {block!r}"
