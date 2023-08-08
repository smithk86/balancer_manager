from enum import StrEnum
from typing import Any

from pydantic import BaseModel, field_validator


class DataUnit(StrEnum):
    BYTE = "B"
    KILOBYTE = "K"
    MEGABYTE = "M"
    GIGABYTE = "G"
    TERABYTE = "T"


class Bytes(BaseModel):
    unit: DataUnit | None = None
    value: float

    @field_validator("unit", mode="before")
    def unit_validator(cls, value: Any) -> Any:
        if value and isinstance(value, str):
            return value[0].upper()
        return None

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
