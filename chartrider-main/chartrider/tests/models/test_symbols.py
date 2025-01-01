from typing import Annotated

from pydantic import BaseModel, BeforeValidator

from chartrider.utils.symbols import Symbol


class _Order(BaseModel):
    @staticmethod
    def decode_symbol(v: str) -> Symbol:
        return Symbol.decode(v)

    symbol: Annotated[Symbol, BeforeValidator(decode_symbol)]


def test_symbol_decoding():
    order = _Order.model_validate({"symbol": "BTC/USDT"})
    assert order.symbol == Symbol.BTC


def test_symbol_decoding_with_colon():
    order = _Order.model_validate({"symbol": "BTC/USDT:USDT"})
    assert order.symbol == Symbol.BTC


def test_symbol_decoding_with_enum():
    order = _Order.model_validate({"symbol": Symbol.BTC})
    assert order.symbol == Symbol.BTC


def test_symbol_is_compatible_with_ccxt():
    assert isinstance(Symbol.BTC, str)
    assert Symbol.BTC.find("/") > -1
    assert Symbol.BTC.split("/")[0] == "BTC"
    assert Symbol.BTC + ":" + "USDT" == "BTC/USDT:USDT"
