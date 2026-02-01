from fastcrud import FastCRUD

from ..models.poem import Poem
from ..schemas.poem import PoemCreateInternal, PoemDelete, PoemRead, PoemUpdate, PoemUpdateInternal

CRUDPoem = FastCRUD[Poem, PoemCreateInternal, PoemUpdate, PoemUpdateInternal, PoemDelete, PoemRead]
crud_poems = CRUDPoem(Poem)
