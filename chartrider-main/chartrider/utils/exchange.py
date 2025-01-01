from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import ccxt
import ccxt.pro
from devtools import debug
from loguru import logger

if TYPE_CHECKING:
    from chartrider.core.common.repository.models import Market

from chartrider.settings import settings
from chartrider.utils.secrets import SecretStore
from chartrider.utils.symbols import Symbol


class ExchangeFactory:
    """
    A factory class that creates and returns a singleton instance of a `ccxt.binance` object
    for a specified testnet mode.
    """

    __public_exchange: dict[bool, ccxt.binanceusdm] = {}
    __public_async_exchange: dict[bool, ccxt.pro.binanceusdm] = {}

    def __init__(self, secret_store: SecretStore) -> None:
        self.__secret_store = secret_store
        self.__exchange: dict[bool, ccxt.binanceusdm] = {}
        self.__async_exchange: dict[bool, ccxt.pro.binanceusdm] = {}

    @classmethod
    def get_public_exchange(cls, use_testnet: bool) -> ccxt.binanceusdm:
        if cls.__public_exchange.get(use_testnet) is None:
            logger.info("Initializing public exchange for the first time.")
            cls.__public_exchange[use_testnet] = cls.__create_exchange(use_testnet=use_testnet)

            cls.warn_if_spot_market()

        return cls.__public_exchange[use_testnet]

    @classmethod
    def get_public_async_exchange(cls, use_testnet: bool) -> ccxt.pro.binanceusdm:
        if cls.__public_async_exchange.get(use_testnet) is None:
            logger.info("Initializing public async exchange for the first time.")
            cls.__public_async_exchange[use_testnet] = cls.__create_exchange(use_testnet=use_testnet, async_mode=True)

            cls.warn_if_spot_market()

        return cls.__public_async_exchange[use_testnet]

    @classmethod
    def close_all_public_exchanges(cls):
        for exchange in cls.__public_async_exchange.values():
            asyncio.run(exchange.close())

    def get_exchange(self, use_testnet: bool) -> ccxt.binanceusdm:
        if self.__exchange.get(use_testnet) is None:
            logger.info("Initializing exchange for the first time.")
            secret = self.__secret_store.get_secret(use_testnet)
            if secret is None:
                raise ValueError("Secret is not set.")

            self.__exchange[use_testnet] = self.__create_exchange(secret.api_key, secret.secret_key, use_testnet)

            self.warn_if_spot_market()

        return self.__exchange[use_testnet]

    def get_async_exchange(self, use_testnet: bool) -> ccxt.pro.binanceusdm:
        if self.__async_exchange.get(use_testnet) is None:
            logger.info("Initializing async exchange for the first time.")
            secret = self.__secret_store.get_secret(use_testnet)
            if secret is None:
                raise ValueError("Secret is not set.")

            self.__async_exchange[use_testnet] = self.__create_exchange(
                secret.api_key, secret.secret_key, use_testnet, async_mode=True
            )

            self.warn_if_spot_market()

        return self.__async_exchange[use_testnet]

    @staticmethod
    def __create_exchange(
        api_key: str | None = None, secret_key: str | None = None, use_testnet: bool = False, async_mode: bool = False
    ) -> Any:
        log = logger.info if use_testnet else logger.warning
        log(f"Creating {'async ' if async_mode else ''}exchange for {'TEST' if use_testnet else 'LIVE'} environment.")

        if async_mode:
            exchange_class = ccxt.pro.binanceusdm
        else:
            exchange_class = ccxt.binanceusdm

        exchange_config: dict[str, Any] = {
            "options": {
                "defaultType": settings.market_type,
                "listenKeyRefreshRate": 10 * 1000,  # 10 seconds
            }
        }
        if api_key is not None and secret_key is not None:
            exchange_config["apiKey"] = api_key
            exchange_config["secret"] = secret_key

        exchange = exchange_class(exchange_config)
        exchange.set_sandbox_mode(use_testnet)

        if not async_mode:
            exchange.load_markets()

        return exchange

    @classmethod
    def amount_to_precision(cls, symbol: Symbol, amount: float) -> float:
        return float(
            cls.get_public_exchange(use_testnet=settings.is_github_action).amount_to_precision(symbol, amount)
        )

    @classmethod
    def price_to_precision(cls, symbol: Symbol, price: float) -> float:
        return float(cls.get_public_exchange(use_testnet=settings.is_github_action).price_to_precision(symbol, price))

    @classmethod
    def get_market(cls, symbol: Symbol) -> Market:
        from chartrider.core.common.repository.models import Market

        exchange = cls.get_public_exchange(use_testnet=settings.is_github_action)
        market = exchange.market(symbol)
        return Market(**market)

    @staticmethod
    def warn_if_spot_market() -> None:
        if settings.market_type == "spot":
            logger.warning(
                "The selected exchange is 'spot', but this program is primarily "
                "designed for the 'futures' market. Please ensure you have chosen "
                "the correct market type."
            )


if __name__ == "__main__":
    secret_store = SecretStore(from_telegram=False).load_from_env(testnet=True)
    exchange = ExchangeFactory(secret_store=secret_store).get_public_exchange(use_testnet=False)
    market = exchange.market("BTC/USDT")
    debug(market)
    ret = exchange.amount_to_precision("BTC/USDT", 0.001)
    debug(ret)
