from chartrider.core.backtest.broker import BacktestBroker
from chartrider.core.backtest.repository import BacktestRepository
from chartrider.core.common.repository.models import (
    MarginMode,
    OrderAction,
    TakerOrMaker,
)
from chartrider.tests.backtest.e2e.conftest import CandleMocker
from chartrider.utils.symbols import Symbol


def test_available_balance_with_isolated_position(
    candle_mocker: CandleMocker,
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
):
    symbol = Symbol.BTC
    price = 10000
    amount = 1
    available_balance_before = backtest_repository.fetch_balance().availableBalance
    fee_amount = price * amount * backtest_repository.get_fee_rate(TakerOrMaker.taker)
    estimated_isolated_wallet = price * amount - fee_amount
    backtest_broker.set_isolated_margin_mode()
    backtest_repository.set_leverage(symbol=symbol, leverage=1)
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    balance = backtest_repository.fetch_balance()
    assert balance.availableBalance == available_balance_before - estimated_isolated_wallet - fee_amount


def test_available_balance_should_remain_same_when_price_changes(
    candle_mocker: CandleMocker,
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
):
    symbol = Symbol.BTC
    price = 10000
    amount = 1

    backtest_broker.set_isolated_margin_mode()
    backtest_repository.set_leverage(symbol=symbol, leverage=1)
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    available_balance_before = backtest_repository.fetch_balance().availableBalance

    # price changes
    candle_mocker.assume_current_candle(close=20000)
    backtest_broker.next()
    candle_mocker.assume_current_candle(close=int(price - 1000))
    backtest_broker.next()

    available_balance_after = backtest_repository.fetch_balance().availableBalance
    assert available_balance_before == available_balance_after


def test_isolated_wallet_should_remain_same_when_price_changes(
    candle_mocker: CandleMocker,
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
):
    symbol = Symbol.BTC
    price = 10000
    amount = 1

    estimated_isolated_wallet = price * amount * (1 - backtest_repository.get_fee_rate(TakerOrMaker.taker))
    backtest_broker.set_isolated_margin_mode()
    backtest_repository.set_leverage(symbol=symbol, leverage=1)
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    long_position = backtest_repository.fetch_positions(symbols=[symbol])[0]
    assert long_position.isolatedWallet == estimated_isolated_wallet

    # price changes
    candle_mocker.assume_current_candle(close=int(price * 2))
    backtest_broker.next()

    long_position = backtest_repository.fetch_positions(symbols=[symbol])[0]
    assert long_position.isolatedWallet == estimated_isolated_wallet


def test_isolated_wallet_should_be_none_in_cross_mode(
    candle_mocker: CandleMocker,
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
):
    symbol = Symbol.BTC
    price = 10000
    amount = 1

    backtest_repository.set_margin_mode(symbol=symbol, margin_mode=MarginMode.cross)
    backtest_repository.set_leverage(symbol=symbol, leverage=1)
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    long_position = backtest_repository.fetch_positions(symbols=[symbol])[0]
    assert long_position.isolatedWallet == 0


def test_isolated_wallet_increase_when_position_added(
    candle_mocker: CandleMocker,
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
):
    symbol = Symbol.BTC
    price = 10000
    amount = 1

    estimated_isolated_wallet = price * amount * (1 - backtest_repository.get_fee_rate(TakerOrMaker.taker))
    backtest_broker.set_isolated_margin_mode()
    backtest_repository.set_leverage(symbol=symbol, leverage=1)
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    long_position = backtest_repository.fetch_positions(symbols=[symbol])[0]
    assert long_position.isolatedWallet == estimated_isolated_wallet

    # add position
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    long_position = backtest_repository.fetch_positions(symbols=[symbol])[0]
    assert long_position.isolatedWallet == estimated_isolated_wallet * 2


def test_isolated_wallet_decrease_when_position_partially_closed(
    candle_mocker: CandleMocker,
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
):
    symbol = Symbol.BTC
    price = 10000
    amount = 1

    backtest_broker.set_isolated_margin_mode()
    backtest_repository.set_leverage(symbol=symbol, leverage=1)
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    long_position = backtest_repository.fetch_positions(symbols=[symbol])[0]
    isolated_wallet = long_position.isolatedWallet

    # close position
    new_price = price * 2
    candle_mocker.assume_current_candle(close=int(new_price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.close_long,
        amount=amount / 2,
        price=new_price,
    )
    backtest_broker.next()

    long_position = backtest_repository.fetch_positions(symbols=[symbol])[0]
    assert long_position.isolatedWallet == isolated_wallet / 2


def test_isolated_wallet_should_be_zero_when_position_closed(
    candle_mocker: CandleMocker,
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
):
    symbol = Symbol.BTC
    price = 10000
    amount = 1

    backtest_broker.set_isolated_margin_mode()
    backtest_repository.set_leverage(symbol=symbol, leverage=1)
    candle_mocker.assume_current_candle(close=int(price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.open_long,
        amount=amount,
        price=price,
    )
    backtest_broker.next()

    # close position
    new_price = price * 2
    candle_mocker.assume_current_candle(close=int(new_price))
    backtest_repository.create_order(
        symbol=symbol,
        action=OrderAction.close_long,
        amount=amount,
        price=new_price,
    )
    backtest_broker.next()

    balance = backtest_repository.fetch_balance()
    assert balance.totalPositionIsolatedMargin == 0
