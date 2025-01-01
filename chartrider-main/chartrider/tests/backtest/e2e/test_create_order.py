import pytest

from chartrider.core.backtest.broker import BacktestBroker
from chartrider.core.backtest.repository import BacktestRepository
from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoBaseRepository,
    ContingentInfoInMemoryRepository,
)
from chartrider.core.common.repository.models import (
    ContingentOrder,
    OrderAction,
    OrderSide,
    PositionSide,
)
from chartrider.tests.backtest.e2e.conftest import CandleMocker
from chartrider.utils.symbols import Symbol


def test_candle_mocker(
    candle_mocker: CandleMocker, backtest_repository: BacktestRepository, backtest_broker: BacktestBroker
):
    timestamp_1 = candle_mocker.assume_current_candle(close=20000, open=21000)
    assert backtest_repository.get_last_price(symbol=Symbol.BTC) == 20000
    assert timestamp_1 == 1
    assert backtest_repository.get_next_timestamp() == timestamp_1
    assert backtest_broker.get_last_ohlcv(symbol=Symbol.BTC) == (21000, 21000 + 1, 20000 - 1, 20000, 1000, timestamp_1)
    timestamp_2 = candle_mocker.assume_current_candle(close=25000)
    assert backtest_repository.get_last_price(symbol=Symbol.BTC) == 25000
    assert timestamp_2 == 2
    assert backtest_repository.get_next_timestamp() == timestamp_2
    assert backtest_broker.get_last_ohlcv(symbol=Symbol.BTC) == (25000, 25000 + 1, 25000 - 1, 25000, 1000, timestamp_2)


def test_create_order(backtest_repository: BacktestRepository, candle_mocker: CandleMocker):
    symbol = Symbol.BTC
    action = OrderAction.open_long
    amount = 0.010
    price = 12345

    candle_mocker.assume_current_candle(close=2000)

    order = backtest_repository.create_order(
        symbol=symbol,
        action=action,
        amount=amount,
        price=price,
    )

    assert order is not None
    assert order.amount == amount
    assert order.price == price
    assert order.side == OrderSide.buy
    assert order.positionSide == PositionSide.long


def test_execute_order(
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
    candle_mocker: CandleMocker,
):
    symbol = Symbol.BTC
    action = OrderAction.open_long
    amount = 1

    candle_mocker.assume_current_candle(close=2000)

    order = backtest_repository.create_order(
        symbol=symbol,
        action=action,
        amount=amount,
        price=2000 - 1,
    )

    assert order is not None
    assert len(backtest_repository.fetch_open_orders(symbol)) == 1

    # nothing should happen
    backtest_broker.next()
    assert len(backtest_repository.fetch_open_orders(symbol)) == 1

    # target price is reached
    candle_mocker.assume_current_candle(close=2000 - 1)

    # order should be executed
    backtest_broker.next()
    assert len(backtest_repository.fetch_open_orders(symbol)) == 0


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_contingent_order(
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
    contingent_repository: ContingentInfoBaseRepository,
    candle_mocker: CandleMocker,
):
    # inject parameterized contingent_repository
    backtest_repository.contingent_repository = contingent_repository

    symbol = Symbol.BTC
    action = OrderAction.open_long
    amount = 1

    price = 2000
    candle_mocker.assume_current_candle(close=int(price) + 1)

    order = backtest_repository.create_order(
        symbol=symbol,
        action=action,
        amount=amount,
        price=price,
        contingent_sl=ContingentOrder(
            triggerPrice=price * 0.5,
        ),
        contingent_tp=ContingentOrder(
            triggerPrice=price * 1.5,
        ),
    )

    # order should be created
    assert order is not None
    assert len(backtest_repository.fetch_orders(symbol)) == 1
    contingent_info = contingent_repository.get_contingent_info(order.id, order.symbol)
    assert contingent_info is not None and not contingent_info.is_triggered

    # nothing should happen
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 1

    # contingent_sl should not be triggered
    candle_mocker.assume_current_candle(close=int(price * 0.6))
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 1
    assert contingent_info is not None and not contingent_info.is_triggered

    # contingent_sl should be triggered
    candle_mocker.assume_current_candle(close=int(price * 0.5))
    backtest_broker.next()
    contingent_info = contingent_repository.get_contingent_info(order.id, order.symbol)
    assert contingent_info is not None and contingent_info.is_triggered and contingent_info.side.isLong
    assert contingent_info.sl_trigger_price is not None  # is SL order


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_invalid_contingent_order(
    backtest_repository: BacktestRepository,
    contingent_repository: ContingentInfoBaseRepository,
    candle_mocker: CandleMocker,
):
    # inject parameterized contingent_repository
    backtest_repository.contingent_repository = contingent_repository

    symbol = Symbol.BTC
    action = OrderAction.open_short
    amount = 1

    price = 2000
    candle_mocker.assume_current_candle(close=int(price) + 1)

    with pytest.raises(AssertionError):
        backtest_repository.create_order(
            symbol=symbol,
            action=action,
            amount=amount,
            price=price,
            contingent_sl=ContingentOrder(
                triggerPrice=price * 0.5,
            ),
            contingent_tp=ContingentOrder(
                triggerPrice=price * 1.5,
            ),
        )


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_contingent_order_short(
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
    contingent_repository: ContingentInfoBaseRepository,
    candle_mocker: CandleMocker,
):
    # inject parameterized contingent_repository
    backtest_repository.contingent_repository = contingent_repository

    symbol = Symbol.BTC
    action = OrderAction.open_short
    amount = 1

    price = 2000
    candle_mocker.assume_current_candle(close=int(price) + 1)

    order = backtest_repository.create_order(
        symbol=symbol,
        action=action,
        amount=amount,
        price=price,
        contingent_sl=ContingentOrder(
            triggerPrice=price * 1.5,
        ),
        contingent_tp=ContingentOrder(
            triggerPrice=price * 0.5,
        ),
    )

    # order should be created
    assert order is not None
    assert len(backtest_repository.fetch_orders(symbol)) == 1
    contingent_info = contingent_repository.get_contingent_info(order.id, order.symbol)
    assert contingent_info is not None and not contingent_info.is_triggered

    # nothing should happen
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 1

    # contingent_tp should not be triggered
    candle_mocker.assume_current_candle(close=int(price * 0.6))
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 1
    assert contingent_info is not None and not contingent_info.is_triggered

    # contingent_tp should be triggered
    candle_mocker.assume_current_candle(close=int(price * 0.5))
    backtest_broker.next()
    contingent_info = contingent_repository.get_contingent_info(order.id, order.symbol)
    assert contingent_info is not None and contingent_info.is_triggered and contingent_info.side.isShort
    assert contingent_info.tp_trigger_price is not None  # is SL order


def test_cancel_contingent_orders(
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
    candle_mocker: CandleMocker,
):
    symbol = Symbol.BTC
    action = OrderAction.open_long
    amount = 1

    price = 2000
    candle_mocker.assume_current_candle(close=int(price))
    order = backtest_repository.create_order(
        symbol=symbol,
        action=action,
        amount=amount,
        price=price,
        contingent_sl=ContingentOrder(
            triggerPrice=price * 0.99,
        ),
        contingent_tp=ContingentOrder(
            triggerPrice=price * 1.01,
        ),
    )
    assert order is not None

    # order should be executed, contingent orders should be created
    backtest_broker.next()
    backtest_repository.cancel_contingent_orders(order)

    # contingent_sl should not be triggered
    candle_mocker.assume_current_candle(close=int(price * 0.5))
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 1


def test_closing_order_canceled_when_position_closed(
    backtest_repository: BacktestRepository,
    backtest_broker: BacktestBroker,
    candle_mocker: CandleMocker,
    contingent_repository: ContingentInfoInMemoryRepository,
):
    symbol = Symbol.BTC
    action = OrderAction.open_long
    amount = 1

    price = 2000
    candle_mocker.assume_current_candle(close=int(price))
    order = backtest_repository.create_order(
        symbol=symbol,
        action=action,
        amount=amount,
        price=price,
        contingent_sl=ContingentOrder(
            triggerPrice=price * 0.5,
        ),
        contingent_tp=ContingentOrder(
            triggerPrice=price * 1.5,
        ),
    )
    assert order is not None

    assert len(contingent_repository.get_pending_contingent_infos()) == 1

    # order should be executed, contingent orders should be created
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 1

    # Close the position by opening an opposite market order
    candle_mocker.assume_current_candle(close=int(price) + 100)
    opposite_order = backtest_repository.create_order(
        symbol=order.symbol, amount=order.amount, action=OrderAction.close_long, price=None
    )
    assert opposite_order is not None
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 2
    assert len(contingent_repository.get_pending_contingent_infos()) == 0

    # Now the contingent orders should be canceled and not be triggered
    candle_mocker.assume_current_candle(close=int(price * 0.5))
    backtest_broker.next()
    assert len(backtest_repository.fetch_orders(symbol)) == 2
