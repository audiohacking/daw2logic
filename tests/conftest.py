"""Shared pytest fixtures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DAWPROJECT_FIXTURE = FIXTURES / "bitwig_simple.dawproject"
BUILD_SCRIPT = FIXTURES / "build_bitwig_simple.py"


@pytest.fixture(scope="session")
def bitwig_simple_dawproject() -> Path:
    if not DAWPROJECT_FIXTURE.is_file():
        subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            check=True,
            cwd=ROOT,
        )
    assert DAWPROJECT_FIXTURE.is_file(), "failed to build bitwig_simple.dawproject"
    return DAWPROJECT_FIXTURE


@pytest.fixture
def logicx_output(tmp_path: Path) -> Path:
    return tmp_path / "out.logicx"
