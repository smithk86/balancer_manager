from abc import abstractmethod
from enum import Enum
from typing import Any, Generator

from pydantic import BaseModel, Field, validator


class ParsableModel(BaseModel):
    _parse_options: Any

    @classmethod
    def parse_payload(cls, payload: str, **kwargs) -> Any:
        pass

    @classmethod
    @abstractmethod
    def _get_parsed_pairs(cls, data: Any, **kwargs) -> Generator[tuple[str, Any], None, None]:
        ...


class DataUnit(str, Enum):
    BYTE = "B"
    KILOBYTE = "K"
    MEGABYTE = "M"
    GIGABYTE = "G"
    TERABYTE = "T"


class Bytes(BaseModel):
    unit: DataUnit | None
    value: float

    @validator("unit", pre=True)
    def unit_validator(cls, v):
        if v:
            return v[0].upper()

    def __int__(self) -> int:
        if self.value == 0 or not self.unit:
            return 0
        elif self.unit == DataUnit.BYTE:
            return int(self.value)
        elif self.unit == DataUnit.KILOBYTE:
            return int(self.value * 1000)
        elif self.unit == DataUnit.MEGABYTE:
            return int(self.value * 1000000)
        elif self.unit == DataUnit.GIGABYTE:
            return int(self.value * 1000000000)
        elif self.unit == DataUnit.TERABYTE:
            return int(self.value * 1000000000000)
        else:
            raise ValueError(f"unit value not supported: {self.unit}")
