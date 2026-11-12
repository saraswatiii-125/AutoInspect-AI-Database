import os
from pathlib import Path
from typing import List

# Ensure backend/vendor is accessible
import app  # noqa: F401

backend_dir = Path(__file__).resolve().parent.parent

# Load .env file from backend directory if present
env_file = backend_dir / ".env"
if env_file.is_file():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key not in os.environ:
                    os.environ[key] = val

class Settings:
    PROJECT_NAME: str = "AutoInspect AI API"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    @property
    def DATABASE_URL(self) -> str:
        """
        Retrieves the Supabase PostgreSQL database connection URL.
        Enforces PostgreSQL with the psycopg 3 driver (postgresql+psycopg://).
        Fails clearly if DATABASE_URL is missing or non-PostgreSQL.
        """
        explicit_url = os.getenv("DATABASE_URL")
        if explicit_url:
            # Check for non-PostgreSQL URLs like SQLite
            scheme = explicit_url.split("://")[0].lower() if "://" in explicit_url else ""
            if scheme in ("sqlite", "mysql", "mssql", "oracle"):
                raise ValueError(
                    f"Unsupported database scheme '{scheme}://'. AutoInspect AI strictly requires "
                    "a Supabase PostgreSQL database. SQLite and other databases are not supported."
                )

            # Normalize PostgreSQL drivers to postgresql+psycopg:// for psycopg 3
            if explicit_url.startswith("postgresql+psycopg://"):
                return explicit_url
            elif explicit_url.startswith("postgresql+psycopg2://"):
                return explicit_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
            elif explicit_url.startswith("postgres://"):
                return explicit_url.replace("postgres://", "postgresql+psycopg://", 1)
            elif explicit_url.startswith("postgresql://"):
                return explicit_url.replace("postgresql://", "postgresql+psycopg://", 1)
            else:
                raise ValueError(
                    f"Invalid DATABASE_URL format. Expected a PostgreSQL connection URL "
                    f"(postgresql+psycopg://<user>:<password>@<host>:<port>/<dbname>), got: {scheme}://..."
                )

        # Check if individual PostgreSQL connection parameters are configured
        has_pg_config = any(
            os.getenv(k) for k in ("POSTGRES_HOST", "POSTGRES_DB")
        )
        if has_pg_config:
            user = os.getenv("POSTGRES_USER", "postgres")
            password = os.getenv("POSTGRES_PASSWORD", "")
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            db = os.getenv("POSTGRES_DB", "postgres")

            if password:
                return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
            return f"postgresql+psycopg://{user}@{host}:{port}/{db}"

        # No fallback to SQLite: fail with clear descriptive error
        raise ValueError(
            "DATABASE_URL is missing. AutoInspect AI strictly requires a Supabase PostgreSQL database. "
            "Please configure DATABASE_URL (e.g. postgresql+psycopg://<user>:<password>@<host>:5432/<dbname>) "
            "in backend/.env."
        )

    @property
    def cors_origins(self) -> List[str]:
        default_origins = [
            "http://localhost:8443",
            "http://127.0.0.1:8443",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
        env_origins = os.getenv("CORS_ORIGINS")
        if env_origins:
            parsed = [o.strip() for o in env_origins.split(",") if o.strip()]
            for origin in parsed:
                if origin == "*":
                    raise ValueError(
                        "Wildcard '*' origin is strictly forbidden when credentialed CORS is enabled. "
                        "Specify exact trusted origins (e.g. http://localhost:8443) in CORS_ORIGINS."
                    )
            return parsed if parsed else default_origins
        return default_origins

    @property
    def allowed_hosts(self) -> List[str]:
        default_hosts = ["localhost", "127.0.0.1", "testserver"]
        env_hosts = os.getenv("ALLOWED_HOSTS")
        if env_hosts:
            parsed = [h.strip() for h in env_hosts.split(",") if h.strip()]
            return parsed if parsed else default_hosts
        return default_hosts

    MAX_REQUEST_SIZE_BYTES: int = int(os.getenv("MAX_REQUEST_SIZE_BYTES", str(15 * 1024 * 1024)))
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")
    RATE_LIMIT_LOGIN_PER_MIN: int = int(os.getenv("RATE_LIMIT_LOGIN_PER_MIN", "10"))
    RATE_LIMIT_REGISTER_PER_MIN: int = int(os.getenv("RATE_LIMIT_REGISTER_PER_MIN", "5"))

    @property
    def JWT_SECRET_KEY(self) -> str:
        """
        Retrieves the JWT signing secret key from the environment.
        Enforces a minimum length of 32 characters for HS256 security.
        Fails safely if missing or insecure.
        """
        secret = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET")
        if not secret:
            raise ValueError(
                "JWT_SECRET_KEY is missing. A secure random secret (at least 32 characters) "
                "must be configured in backend/.env for JWT authentication."
            )
        if len(secret) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY is insecure. Length is {len(secret)} characters, "
                "but at least 32 characters (256 bits) are strictly required for HS256 security."
            )
        return secret

    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

settings = Settings()
