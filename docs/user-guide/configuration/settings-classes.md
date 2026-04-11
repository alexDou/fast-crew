# Settings Classes

`src/app/core/config.py` is the backend's configuration schema. Runtime values come from `src/.env`, and application code should read them through the shared `settings` instance instead of duplicating literals in feature modules.

## Source Of Truth

The current configuration pipeline is:

1. `src/.env` stores environment-specific values.
2. `Settings` in `src/app/core/config.py` parses and validates them.
3. The rest of the app imports `settings` and uses either raw fields or computed fields.

Derived values such as PostgreSQL URLs are intentionally built inside `Settings` so the connection details still come from `.env` in one place.

## Env File Loading

The backend loads settings from `src/.env` using:

```python
model_config = SettingsConfigDict(
    env_file=ENV_FILE_PATH,
    env_file_encoding="utf-8",
    case_sensitive=True,
    env_ignore_empty=True,
    env_parse_none_str="None",
    extra="ignore",
)
```

`extra="ignore"` is intentional today because the repository may also keep non-app secrets in the same `.env` for CrewAI tooling. Application code should still only consume fields declared in `Settings`.

## Current Settings Composition

The main settings object inherits from these groups:

```python
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
    ...
```

## Current Settings Groups

### Application Metadata

```python
class AppSettings(BaseSettings):
    APP_NAME: str
    APP_DESCRIPTION: str | None
    APP_VERSION: str | None
    LICENSE_NAME: str | None
    CONTACT_NAME: str | None
    CONTACT_EMAIL: str | None
```

Used by the OpenAPI metadata and health endpoints.

### JWT And Auth

```python
class CryptSettings(BaseSettings):
    SECRET_KEY: SecretStr
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
```

Used by `src/app/core/security.py` and the login/refresh/logout routes.

### PostgreSQL

```python
class PostgresSettings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_SYNC_PREFIX: str
    POSTGRES_ASYNC_PREFIX: str

    @computed_field
    @property
    def POSTGRES_URI(self) -> str:
        credentials = f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
        location = f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return f"{credentials}@{location}"

    @computed_field
    @property
    def POSTGRES_SYNC_DATABASE_URL(self) -> str:
        return f"{self.POSTGRES_SYNC_PREFIX}{self.POSTGRES_URI}"

    @computed_field
    @property
    def POSTGRES_ASYNC_DATABASE_URL(self) -> str:
        return f"{self.POSTGRES_ASYNC_PREFIX}{self.POSTGRES_URI}"
```

This is the current single source of truth for database connection construction.

### Admin Bootstrap User

```python
class FirstUserSettings(BaseSettings):
    ADMIN_NAME: str
    ADMIN_EMAIL: str
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str
```

Used by CRUDAdmin initialization and bootstrap flows.

### Redis And Client Cache

```python
class RedisCacheSettings(BaseSettings):
    REDIS_CACHE_HOST: str
    REDIS_CACHE_PORT: int

    @computed_field
    @property
    def REDIS_CACHE_URL(self) -> str:
        return f"redis://{self.REDIS_CACHE_HOST}:{self.REDIS_CACHE_PORT}"


class ClientSideCacheSettings(BaseSettings):
    CLIENT_CACHE_MAX_AGE: int


class RedisQueueSettings(BaseSettings):
    REDIS_QUEUE_HOST: str
    REDIS_QUEUE_PORT: int
```

`REDIS_CACHE_URL` is used by the app cache pool. Queue workers still consume host and port separately because `arq.RedisSettings` expects them that way.

### Storage

```python
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
```

Used by `src/app/services/storage_service.py` for both local and S3-backed media/output storage.

### LLM Provider Access

```python
class OpenRouterSettings(BaseSettings):
    OPENROUTER_API_KEY: SecretStr | None
```

This is the only LLM key currently consumed by the FastAPI app code. The CrewAI bundle may have additional tooling-specific env vars, but they are not part of the backend `Settings` schema unless the app itself reads them.

### Email Delivery

```python
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
```

Used by the verification email service and email-verification flow.

### CRUDAdmin

```python
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
```

`SESSION_SECURE_COOKIES` is also used by the login route for the refresh-token cookie, so cookie security now comes from `.env` instead of a hardcoded value.

### Environment And CORS

```python
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
```

Used by application setup, health responses, and email-verification URL fallbacks.

### Logging

```python
class FileLoggerSettings(BaseSettings):
    FILE_LOG_MAX_BYTES: int
    FILE_LOG_BACKUP_COUNT: int
    FILE_LOG_FORMAT_JSON: bool
    FILE_LOG_LEVEL: str
    FILE_LOG_INCLUDE_REQUEST_ID: bool
    FILE_LOG_INCLUDE_PATH: bool
    FILE_LOG_INCLUDE_METHOD: bool
    FILE_LOG_INCLUDE_CLIENT_HOST: bool
    FILE_LOG_INCLUDE_STATUS_CODE: bool


class ConsoleLoggerSettings(BaseSettings):
    CONSOLE_LOG_LEVEL: str
    CONSOLE_LOG_FORMAT_JSON: bool
    CONSOLE_LOG_INCLUDE_REQUEST_ID: bool
    CONSOLE_LOG_INCLUDE_PATH: bool
    CONSOLE_LOG_INCLUDE_METHOD: bool
    CONSOLE_LOG_INCLUDE_CLIENT_HOST: bool
    CONSOLE_LOG_INCLUDE_STATUS_CODE: bool
```

Used by `src/app/core/logger.py`.

## Rules For Adding New Settings

When you add a new application setting:

1. Add the field to the appropriate `BaseSettings` group in `src/app/core/config.py`.
2. Add the value to `src/.env` and any deployment example files that should carry it.
3. Read it through `settings`, not through `os.getenv()` or duplicated module constants.
4. Only use computed fields for derived values such as URLs assembled from env-backed parts.

## What To Avoid

- Hardcoding connection strings outside `Settings`
- Mirroring env values into separate module-level config constants when `settings` can be used directly
- Reading app config with `os.getenv()` from route or service modules
- Letting docs describe settings groups that no longer exist

## Quick Audit Checklist

Use this when refactoring config-related code:

1. Is every app-consumed env variable declared in `Settings`?
2. Is the value read via `settings` everywhere in app code?
3. Is a computed field used only for derivation, not as a second source of truth?
4. Do `.env` examples and docs match the current schema?
