import hashlib
from pathlib import Path
from typing import Self

import click
from loguru import logger
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict as ConfigDict

from chartrider.settings import ROOT_PATH, settings


class Secret(BaseSettings):
    api_key: str = ""
    secret_key: str = ""

    model_config = ConfigDict(env_file_encoding="utf-8")

    @property
    def is_valid(self) -> bool:
        return bool(self.api_key) and bool(self.secret_key)

    def hash(self) -> str:
        return hashlib.md5(f"{self.api_key}{self.secret_key}".encode()).hexdigest()


class SecretStore:
    def __init__(self, from_telegram: bool) -> None:
        self.from_telegram = from_telegram
        self.__secrets: dict[bool, Secret] = dict()

    def get_secret(self, use_testnet: bool) -> Secret | None:
        if not use_testnet:
            logger.warning("Your secrets for the mainnet is being accessed.")
        secret = self.__secrets.get(use_testnet)
        if secret is not None:
            return secret
        if self.from_telegram:
            return None
        self.load_from_env(use_testnet)
        return self.__secrets[use_testnet]

    def set_secret(self, use_testnet: bool, secret: Secret) -> None:
        self.__secrets[use_testnet] = secret

    def load_from_env(self, testnet: bool) -> Self:
        secret = self.__read_from_env(testnet)
        if secret is None:
            self.__handle_missing_or_empty_secrets(testnet)
            secret = self.__read_from_env(testnet)
            assert secret is not None
        self.__secrets[testnet] = secret
        return self

    def __read_from_env(self, testnet: bool) -> Secret | None:
        secret = Secret(_env_file=self.__get_env_file_path(testnet))  # type: ignore
        if not secret.is_valid:
            return None
        return secret

    def __get_env_file_path(self, testnet: bool) -> tuple[Path, Path]:
        env_name = "test" if testnet else "main"
        env_file_path = ROOT_PATH / f".secret.{env_name}"
        local_env_path = env_file_path.with_suffix(env_file_path.suffix + ".local")
        return env_file_path, local_env_path

    def __handle_missing_or_empty_secrets(self, testnet: bool) -> None:
        if settings.is_github_action:
            raise ValueError("Required environment variables are missing. Please set `API_KEY` and `SECRET_KEY`.")
        else:
            env_name = "test" if testnet else "main"
            _, local_env_path = self.__get_env_file_path(testnet)
            logger.info(f"Secrets file '{local_env_path}' not found or invalid.")
            api_key = click.prompt(f"Enter API key ({env_name}): ", type=str)
            secret_key = click.prompt(f"Enter secret key ({env_name}): ", type=str)

            with local_env_path.open("w") as f:
                f.write(f"API_KEY={api_key}\n")
                f.write(f"SECRET_KEY={secret_key}\n")
