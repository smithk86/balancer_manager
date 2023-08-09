import pytest
from pydantic import ValidationError

from httpd_manager.models import Bytes


@pytest.mark.parametrize(
    "bytes_,int_",
    [
        (Bytes(value="51", unit="B"), 51),
        (Bytes(value="5.1", unit="kB"), 5100),
        (Bytes(value="5.1", unit="K"), 5100),
        (Bytes(value="5.1", unit="MB"), 5100000),
        (Bytes(value="5.1", unit="GB"), 5100000000),
        (Bytes(value="5.1", unit="TB"), 5100000000000),
    ],
)
def test_bytes(bytes_: bytes, int_: int) -> None:
    assert int(bytes_) == int_


def test_bytes_bad_unit() -> None:
    with pytest.raises(ValidationError, match=r".*validation error for Bytes.*"):
        Bytes(value=51, unit="zb")

    with pytest.raises(ValidationError, match=r".*Input should be a valid number.*"):
        Bytes(value=None, unit="K")
