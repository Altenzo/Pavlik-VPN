from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from typing import List

class Settings(BaseSettings):
    # Bot Settings
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int] = Field(default_factory=list)

    # Database Settings
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASS: str = "postgres"
    DB_NAME: str = "vpn_bot"

    @property
    def db_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Redis Settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # VPN Panel Settings
    PANEL_URL: str
    PANEL_USERNAME: str
    PANEL_PASSWORD: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Extra fields will be ignored
        extra="ignore"
    )

config = Settings()
