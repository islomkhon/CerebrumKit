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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

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
