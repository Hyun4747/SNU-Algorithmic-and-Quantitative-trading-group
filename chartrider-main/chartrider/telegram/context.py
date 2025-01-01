from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from telegram.ext import ContextTypes

from chartrider.core.strategy.presets import StrategyPreset
from chartrider.utils.secrets import Secret, SecretStore


class TelegramUserContext(BaseModel):
    username: str | None = None
    temp_secret_key: str | None = None
    temp_api_key: str | None = None
    testnet: bool | None = None

    secret_store: SecretStore
    strategy_preset: StrategyPreset | None = None

    input_pending_broker_names: dict[bool, str]
    container_ids: dict[bool, str]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data):
        super().__init__(
            secret_store=SecretStore(from_telegram=True),
            input_pending_broker_names={},
            container_ids={},
            **data,
        )

    def clear(self, context: ContextTypes.DEFAULT_TYPE):
        self.temp_api_key, self.temp_secret_key = None, None
        self.save(context)

    def save(self, context: ContextTypes.DEFAULT_TYPE):
        assert context.user_data is not None
        context.user_data["context"] = self

    def save_secret_from_input(self, context: ContextTypes.DEFAULT_TYPE) -> Secret | None:
        if self.temp_api_key is None or self.temp_secret_key is None or self.testnet is None:
            return None
        secret = Secret(
            api_key=self.temp_api_key,
            secret_key=self.temp_secret_key,
        )
        self.secret_store.set_secret(self.testnet, secret)
        self.temp_api_key, self.temp_secret_key = None, None
        self.save(context)
        return secret

    def get_message_queue_name(self) -> str | None:
        if self.testnet is None:
            return None
        return self.get_message_queue_name_by(self.testnet)

    def get_message_queue_name_by(self, testnet: bool):
        secret = self.secret_store.get_secret(testnet)
        if secret is None:
            return None
        return secret.hash()

    @property
    def input_pending_broker_name(self) -> str | None:
        if self.testnet is None:
            return None
        return self.input_pending_broker_names.get(self.testnet)

    def set_input_pending_broker_name(self, value: str | None):
        assert self.testnet is not None
        if value is None:
            self.input_pending_broker_names.pop(self.testnet, None)
            return
        self.input_pending_broker_names[self.testnet] = value

    @property
    def container_id(self) -> str | None:
        if self.testnet is None:
            return None
        return self.container_ids.get(self.testnet)

    def set_container_id(self, value: str | None):
        assert self.testnet is not None
        if value is None:
            self.container_ids.pop(self.testnet, None)
            return
        self.container_ids[self.testnet] = value

    def set_container_id_by(self, testnet: bool, value: str | None):
        if value is None:
            self.container_ids.pop(testnet, None)
            return
        self.container_ids[testnet] = str(value)

    @property
    def environment(self) -> str:
        if self.testnet is None:
            return "N/A"
        return "testnet" if self.testnet else "mainnet"

    @classmethod
    def is_compatible(cls, other_context: BaseModel) -> bool:
        if not isinstance(other_context, TelegramUserContext):
            return False
        return cls.model_fields.keys() == other_context.model_fields.keys()


def get_user_context(context: ContextTypes.DEFAULT_TYPE) -> TelegramUserContext:
    assert context.user_data is not None
    user_context = context.user_data.setdefault("context", TelegramUserContext())
    assert isinstance(user_context, TelegramUserContext)
    if not TelegramUserContext.is_compatible(user_context):
        new_context = TelegramUserContext()
        context.user_data["context"] = new_context
        return new_context
    return user_context
