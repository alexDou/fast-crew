from crudadmin import CRUDAdmin
from crudadmin.admin_interface.model_view import PasswordTransformer

from ..core.security import get_password_hash
from ..models.poem import Poem
from ..models.poem_source import PoemSource
from ..models.user import User
from ..schemas.poem import PoemCreate, PoemUpdate
from ..schemas.poem_source import PoemSourceCreate, PoemSourceUpdate
from ..schemas.user import UserCreate, UserCreateInternal, UserUpdate


def register_admin_views(admin: CRUDAdmin) -> None:
    """Register all models and their schemas with the admin interface.

    This function adds all available models to the admin interface with appropriate
    schemas and permissions.
    """

    password_transformer = PasswordTransformer(
        password_field="password",
        hashed_field="hashed_password",
        hash_function=get_password_hash,
        required_fields=["name", "username", "email"],
    )

    admin.add_view(
        model=User,
        create_schema=UserCreate,
        update_schema=UserUpdate,
        update_internal_schema=UserCreateInternal,
        password_transformer=password_transformer,
        allowed_actions={"view", "create", "update"},
    )

    # Staged workflow debugging: admins need to inspect image_analysis,
    # follow_up_questions / follow_up_answers and error_message without being
    # able to mutate them from the UI (workflow transitions are strictly
    # owned by the CrewAI service).
    admin.add_view(
        model=PoemSource,
        create_schema=PoemSourceCreate,
        update_schema=PoemSourceUpdate,
        allowed_actions={"view"},
    )

    # Generated poems are view-only from the admin panel; workflow writes are
    # owned by the CrewAI service.
    admin.add_view(
        model=Poem,
        create_schema=PoemCreate,
        update_schema=PoemUpdate,
        allowed_actions={"view"},
    )
