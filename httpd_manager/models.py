import re
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Pattern, Tuple

import dateparser
from pydantic import BaseModel, Field, validator


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
