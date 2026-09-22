import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Placeholder secrets that must never be used to sign real sessions.
_INSECURE_SECRETS = {"", "change-me", "change-me-to-a-random-string"}


class Settings(BaseSettings):
    database_url: str = "sqlite:///./cerebrumkit.db"  # override with postgresql:// for prod
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # Additional browser origins allowed to call this API, written as one regular
    # expression, e.g. `https://.*[.]example[.]dev`. Empty by default, because a
    # local checkout only ever talks to the localhost origins listed in main.py.
    # It exists for an install reached through a hostname that cannot be written
    # down in advance, such as a forwarded Codespace URL - see
    # .devcontainer/start.sh, which sets it from the container's own domain.
    cors_origin_regex: str = ""

    # The accounts seed.py creates on a fresh install. They are declared here
    # rather than read with os.getenv because a value written in backend/.env
    # reaches this settings object and never reaches the process environment, so
    # os.getenv cannot see it - and the README tells you to put them in .env.
    # The first three have no fallback anywhere: the seeder refuses to create an
    # account until they are set.
    seed_admin_email: str = ""
    seed_client_email: str = ""
    seed_password: str = ""
    seed_admin_country: str = "CN"
    seed_client_country: str = "CN"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Anything else in the environment or in that file is ignored. Without
        # this, pydantic-settings refuses to build Settings at all when it meets
        # a variable it does not know. That is not a warning: it raises, so
        # setting SEED_ADMIN_EMAIL the way the README describes stopped
        # migrate.py - and the whole seeder, and the server - from starting.
        extra = "ignore"

    @model_validator(mode="after")
    def _warn_on_insecure_secret(self) -> "Settings":
        if self.secret_key in _INSECURE_SECRETS:
            logger.warning(
                "SECRET_KEY is unset or still the default placeholder, so JWTs are "
                "trivially forgeable. Set a strong random SECRET_KEY in backend/.env "
                "(see backend/.env.example) before exposing this API."
            )
        return self


settings = Settings()