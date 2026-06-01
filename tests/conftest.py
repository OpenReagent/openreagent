import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "contracts"


@pytest.fixture
def fixtures_dir() -> str:
    return str(FIXTURES)


@pytest.fixture
def fixtures_path() -> pathlib.Path:
    return FIXTURES
