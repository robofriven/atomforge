# common.py
from typing import Union
from .atoms import AtomId

NameOrId = Union[str, AtomId]


class ByLabelCreationError(ValueError):
    pass
