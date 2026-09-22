"""Verdent Platform — environment variables (pydantic-settings).

Every setting maps 1:1 to `env.example` at the repo root. In Railway, the
same names go under each service's Variables tab. DATABASE_URL / REDIS_URL
are injected by the Postgres/Redis add-ons; the Postgres variable arrives as
`postgresql://...` and is normalized here to the asyncpg driver.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_postgres_url(url: str) -> str:
    """postgresql://... -> postgresql+asyncpg://... (asyncpg is the only driver)."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- 1. REQUIRED -------------------------------------------------------
    telegram_bot_token: str = ""
    telegram_owner_id: int | None = None
    subscription_base_url: str = ""

    # --- 2. Auto-provided by Railway ---------------------------------------
    database_url: str = "postgresql://user:password@localhost:5432/verdent_platform"
    redis_url: str = "redis://localhost:6379/0"
    port: int = 8080

    # --- 3. Generated once, kept secret ------------------------------------
    telegram_webhook_secret_token: str = ""
    jwt_signing_key: str = ""
    cloudflare_token_encryption_key: str = ""   # base64, decodes to exactly 32 bytes
    node_hmac_secret_pepper: str = ""

    # --- 4. Safe defaults ---------------------------------------------------
    environment: str = "development"
    telegram_login_widget_bot_username: str = ""
    r2_bucket_name: str = "bpb-payment-proofs"
    stars_enabled: bool = False

    # --- 5. Manual payment (shown to customers on the payment screen) -------
    payment_card_number: str = ""
    payment_card_holder: str = ""
    payment_instructions: str = ""

    # --- 6. Data plane -------------------------------------------------------
    # Durable Objects need Workers Paid; on free plans leave false and the
    # Node degrades to fail-open session checks (warning logged at the edge).
    nodes_enable_durable_objects: bool = False
    # Deployed fork bundle uploaded to Cloudflare at provisioning time.
    node_worker_bundle_path: str = "assets/worker_bundle.js"

    @property
    def async_database_url(self) -> str:
        return _normalize_postgres_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
