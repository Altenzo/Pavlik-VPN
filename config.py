from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from typing import List, Optional


class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    ADMIN_IDS: List[int] = Field(default_factory=list)
    DEBUG: bool = False

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASS: str = "postgres"
    DB_NAME: str = "vpn_bot"
    DATABASE_URL: Optional[str] = None  # если задан — используется вместо DB_*

    @property
    def db_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    PANEL_URL: str
    PANEL_API_TOKEN: str
    PANEL_INBOUND_UUID: str = ""

    PLATEGA_MERCHANT_ID: str
    PLATEGA_SECRET: str

    INTERNAL_SQUAD_UUIDS: List[str] = Field(default_factory=list)
    EXTERNAL_SQUAD_UUID: Optional[str] = None

    REFERRAL_COMMISSION_RATE: float = 0.20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


config = Settings()
