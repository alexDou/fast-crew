from enum import Enum
from pathlib import Path

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"


class AppSettings(BaseSettings):
    APP_NAME: str
    APP_DESCRIPTION: str | None
    APP_VERSION: str | None
    LICENSE_NAME: str | None
    CONTACT_NAME: str | None
    CONTACT_EMAIL: str | None


class CryptSettings(BaseSettings):
    SECRET_KEY: SecretStr
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int


class FileLoggerSettings(BaseSettings):
    FILE_LOG_MAX_BYTES: int
    FILE_LOG_BACKUP_COUNT: int
    FILE_LOG_FORMAT_JSON: bool
    FILE_LOG_LEVEL: str

    # Include request ID, path, method, client host, and status code in the file log
    FILE_LOG_INCLUDE_REQUEST_ID: bool
    FILE_LOG_INCLUDE_PATH: bool
    FILE_LOG_INCLUDE_METHOD: bool
    FILE_LOG_INCLUDE_CLIENT_HOST: bool
    FILE_LOG_INCLUDE_STATUS_CODE: bool


class ConsoleLoggerSettings(BaseSettings):
    CONSOLE_LOG_LEVEL: str
    CONSOLE_LOG_FORMAT_JSON: bool

    # Include request ID, path, method, client host, and status code in the console log
    CONSOLE_LOG_INCLUDE_REQUEST_ID: bool
    CONSOLE_LOG_INCLUDE_PATH: bool
    CONSOLE_LOG_INCLUDE_METHOD: bool
    CONSOLE_LOG_INCLUDE_CLIENT_HOST: bool
    CONSOLE_LOG_INCLUDE_STATUS_CODE: bool


class DatabaseSettings(BaseSettings):
    pass


class PostgresSettings(DatabaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_SYNC_PREFIX: str
    POSTGRES_ASYNC_PREFIX: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def POSTGRES_URI(self) -> str:
        credentials = f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
        location = f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return f"{credentials}@{location}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def POSTGRES_SYNC_DATABASE_URL(self) -> str:
        return f"{self.POSTGRES_SYNC_PREFIX}{self.POSTGRES_URI}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def POSTGRES_ASYNC_DATABASE_URL(self) -> str:
        return f"{self.POSTGRES_ASYNC_PREFIX}{self.POSTGRES_URI}"


class FirstUserSettings(BaseSettings):
    ADMIN_NAME: str
    ADMIN_EMAIL: str
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str


class RedisCacheSettings(BaseSettings):
    REDIS_CACHE_HOST: str
    REDIS_CACHE_PORT: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_CACHE_URL(self) -> str:
        return f"redis://{self.REDIS_CACHE_HOST}:{self.REDIS_CACHE_PORT}"


class ClientSideCacheSettings(BaseSettings):
    CLIENT_CACHE_MAX_AGE: int


class RedisQueueSettings(BaseSettings):
    REDIS_QUEUE_HOST: str
    REDIS_QUEUE_PORT: int


class StorageSettings(BaseSettings):
    STORAGE_BACKEND: str
    LOCAL_STORAGE_ROOT: str

    S3_BUCKET_NAME: str | None
    S3_REGION: str
    S3_ENDPOINT_URL: str | None
    S3_MEDIA_PREFIX: str
    S3_OUTPUT_PREFIX: str
    S3_SIGNED_URL_EXPIRE_SECONDS: int

    AWS_ACCESS_KEY_ID: str | None
    AWS_SECRET_ACCESS_KEY: str | None
    AWS_SESSION_TOKEN: str | None
    AWS_PROFILE: str | None


class OpenRouterSettings(BaseSettings):
    OPENROUTER_API_KEY: SecretStr | None


class EmailSettings(BaseSettings):
    SMTP_HOST: str | None
    SMTP_PORT: int
    SMTP_USERNAME: str | None
    SMTP_PASSWORD: SecretStr | None
    SMTP_USE_STARTTLS: bool
    SMTP_USE_SSL: bool
    SMTP_TIMEOUT_SECONDS: int

    EMAIL_FROM_NAME: str
    EMAIL_FROM_ADDRESS: str | None
    EMAIL_REPLY_TO: str | None
    EMAIL_VERIFICATION_BASE_URL: str | None
    EMAIL_VERIFICATION_EXPIRE_DAYS: int


class CRUDAdminSettings(BaseSettings):
    CRUD_ADMIN_ENABLED: bool
    CRUD_ADMIN_MOUNT_PATH: str

    CRUD_ADMIN_ALLOWED_IPS_LIST: list[str] | None
    CRUD_ADMIN_ALLOWED_NETWORKS_LIST: list[str] | None
    CRUD_ADMIN_MAX_SESSIONS: int
    CRUD_ADMIN_SESSION_TIMEOUT: int
    SESSION_SECURE_COOKIES: bool

    CRUD_ADMIN_TRACK_EVENTS: bool
    CRUD_ADMIN_TRACK_SESSIONS: bool

    CRUD_ADMIN_REDIS_ENABLED: bool
    CRUD_ADMIN_REDIS_HOST: str
    CRUD_ADMIN_REDIS_PORT: int
    CRUD_ADMIN_REDIS_DB: int
    CRUD_ADMIN_REDIS_PASSWORD: str | None
    CRUD_ADMIN_REDIS_SSL: bool


class EnvironmentOption(str, Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class EnvironmentSettings(BaseSettings):
    ENVIRONMENT: EnvironmentOption


class CORSSettings(BaseSettings):
    CORS_ORIGINS: list[str]
    CORS_METHODS: list[str]
    CORS_HEADERS: list[str]


class Settings(
    AppSettings,
    PostgresSettings,
    CryptSettings,
    FirstUserSettings,
    RedisCacheSettings,
    ClientSideCacheSettings,
    RedisQueueSettings,
    StorageSettings,
    OpenRouterSettings,
    EmailSettings,
    CRUDAdminSettings,
    EnvironmentSettings,
    CORSSettings,
    FileLoggerSettings,
    ConsoleLoggerSettings,
):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_ignore_empty=True,
        env_parse_none_str="None",
        extra="ignore",
    )


# pydantic-settings loads required fields from the environment at runtime,
# but mypy treats the generated __init__ like a normal required-args constructor.
settings = Settings()  # type: ignore[call-arg]
