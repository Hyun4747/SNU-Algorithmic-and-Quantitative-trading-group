import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict as ConfigDict

ROOT_PATH = Path(__file__).parent.parent
PERSISTENCE_PATH = ROOT_PATH / "persistence"
DB_PATH = PERSISTENCE_PATH / "database"
LOG_PATH = PERSISTENCE_PATH / "logs"
REPORTS_PATH = ROOT_PATH / "reports"
BACKTEST_REPORTS_PATH = REPORTS_PATH / "backtest"


class Settings(BaseSettings):
    stake_currency: str = "USDT"
    market_type: Literal["spot", "future"] = "future"
    is_github_action: bool = os.getenv("GITHUB_ACTIONS") == "true"
    ecr_repository: str = "542695926028.dkr.ecr.ap-northeast-2.amazonaws.com"


class PostgresSettings(BaseSettings):
    username: str = "postgres"
    password: str = "postgres"
    host: str = "localhost"
    port: int = 5432
    name: str = "postgres"
    max_pool_size: int = 100  # pg default max connection
    pool_pre_ping: bool = True  # check connection before using

    model_config = ConfigDict(case_sensitive=False, env_prefix="postgres_")

    @property
    def url(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def test_url(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:5433/test"


class RabbitMQSettings(BaseSettings):
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    model_config = ConfigDict(case_sensitive=False, env_prefix="rabbitmq_")

    @property
    def url(self) -> str:
        return f"amqp://{self.username}:{self.password}@{self.host}:{self.port}"


class TelegramSettings(BaseSettings):
    token: str = ""
    beta_token: str = ""
    debug: bool = True

    model_config = ConfigDict(
        env_prefix="telegram_",
        env_file_encoding="utf-8",
        env_file=(
            ROOT_PATH / ".secret.telegram",
            ROOT_PATH / ".secret.telegram.local",
        ),
    )


settings = Settings()
rabbitmq_settings = RabbitMQSettings()
telegram_settings = TelegramSettings()
postgres_settings = PostgresSettings()
