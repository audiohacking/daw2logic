"""Shared pytest fixtures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BUILD_SCRIPT = FIXTURES / "build_bitwig_simple.py"


@pytest.fixture(scope="session")
def bitwig_simple_dawproject() -> Path:
    path = FIXTURES / "bitwig_simple.dawproject"
    if not path.is_file():
        subprocess.run([sys.executable, str(BUILD_SCRIPT)], check=True, cwd=ROOT)
    assert path.is_file()
    return path


@pytest.fixture(scope="session")
def bitwig_extended_dawproject() -> Path:
    path = FIXTURES / "bitwig_extended.dawproject"
    if not path.is_file():
        subprocess.run([sys.executable, str(BUILD_SCRIPT)], check=True, cwd=ROOT)
    assert path.is_file()
    return path


@pytest.fixture
def logicx_output(tmp_path: Path) -> Path:
    return tmp_path / "out.logicx"
