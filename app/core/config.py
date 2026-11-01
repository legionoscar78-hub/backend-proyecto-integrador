from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"  # backend/.env


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str

    # Clave con la que se firman los tokens de sesión. Sin valor por defecto a propósito: si falta
    # o es corta, la aplicación no arranca. Genera una con:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: str = Field(min_length=32)
    access_token_minutes: int = Field(default=60, ge=1, le=1440)

    model_config = SettingsConfigDict(env_file=ENV_FILE)

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()