from fastcrud import FastCRUD

from ..models.poem_source import PoemSource
from ..schemas.poem_source import (
    PoemSourceCreateInternal,
    PoemSourceDelete,
    PoemSourceRead,
    PoemSourceUpdate,
    PoemSourceUpdateInternal,
)

CRUDPoemSource = FastCRUD[
    PoemSource,
    PoemSourceCreateInternal,
    PoemSourceUpdate,
    PoemSourceUpdateInternal,
    PoemSourceDelete,
    PoemSourceRead,
]
crud_poem_sources = CRUDPoemSource(PoemSource)
