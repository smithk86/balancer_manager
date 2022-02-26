import pytest

from httpd_manager.helpers import Bytes


@pytest.mark.parametrize(
    "bytes_,int_",
    [
        (Bytes(51, "B"), 51),
        (Bytes(5.1, "kB"), 5100),
        (Bytes(5.1, "K"), 5100),
        (Bytes(5.1, "MB"), 5100000),
        (Bytes(5.1, "GB"), 5100000000),
        (Bytes(5.1, "TB"), 5100000000000),
    ],
)
def test_bytes(bytes_, int_):
    assert int(bytes_) == int_


def test_bytes_bad_unit():
    bytes_ = Bytes(51, "zb")
    with pytest.raises(ValueError) as excinfo:
        int(bytes_)
    assert "unit value not supported: Z" == str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        Bytes(None, "K")
    assert "raw value must be int or float" == str(excinfo.value)
