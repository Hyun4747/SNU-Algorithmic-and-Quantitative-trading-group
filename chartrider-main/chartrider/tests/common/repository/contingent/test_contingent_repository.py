import pytest

from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoBaseRepository,
)
from chartrider.core.common.repository.models import ContingentOrder, PositionSide
from chartrider.utils.symbols import Symbol


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_trigger_contingent_info(
    contingent_repository: ContingentInfoBaseRepository,
):
    order_id = "123"
    symbol = Symbol.BTC
    contingent_repository.create_contingent_info(
        order_id=order_id,
        side=PositionSide.long,
        symbol=Symbol.BTC,
        contingent_sl=ContingentOrder(triggerPrice=1000),
    )
    contingent_repository.mark_contingent_info_as_triggered(order_id=order_id, symbol=symbol)
    contingent_info = contingent_repository.get_contingent_info(order_id=order_id, symbol=symbol)
    assert contingent_info is not None
    assert contingent_info.is_triggered


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_create_and_retrieve_contingent_info(contingent_repository: ContingentInfoBaseRepository):
    order_id = "create_test"
    symbol = Symbol.BTC
    contingent_repository.create_contingent_info(order_id, symbol, PositionSide.long)
    contingent_info = contingent_repository.get_contingent_info(order_id, symbol=symbol)
    assert contingent_info is not None
    assert contingent_info.order_id == order_id
    assert contingent_info.symbol == symbol
    assert contingent_info.side == PositionSide.long


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_delete_contingent_info(contingent_repository: ContingentInfoBaseRepository):
    order_id = "delete_test"
    symbol = Symbol.BTC
    contingent_repository.create_contingent_info(order_id, symbol, PositionSide.long)
    contingent_repository.delete_contingent_info(order_id, symbol)
    contingent_info = contingent_repository.get_contingent_info(order_id, symbol)
    assert contingent_info is None


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_get_all_contingent_infos(contingent_repository: ContingentInfoBaseRepository):
    order_ids = ["order1", "order2", "order3"]
    for oid in order_ids:
        contingent_repository.create_contingent_info(oid, Symbol.BTC, PositionSide.long)
    all_contingent_infos = contingent_repository.get_all_contingent_infos()
    assert len(all_contingent_infos) == len(order_ids)


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_delete_pending_by_symbol(contingent_repository: ContingentInfoBaseRepository):
    symbol = Symbol.BTC
    order_id1 = "pending_1"
    order_id2 = "pending_2"
    contingent_repository.create_contingent_info(order_id1, symbol, PositionSide.long)
    contingent_repository.create_contingent_info(order_id2, symbol, PositionSide.long)
    contingent_repository.delete_pending_contingent_infos(symbol, PositionSide.long)
    contingent_infos = contingent_repository.get_all_contingent_infos()
    assert len(contingent_infos) == 0


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_delete_pending_contingent_info_with_multiple_symbols(contingent_repository: ContingentInfoBaseRepository):
    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("btc-2", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("eth-1", Symbol.ETH, PositionSide.long)
    contingent_repository.create_contingent_info("eth-2", Symbol.ETH, PositionSide.long)

    contingent_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)
    contingent_repository.mark_contingent_info_as_triggered("eth-1", Symbol.ETH)

    contingent_repository.delete_pending_contingent_infos(Symbol.BTC, PositionSide.long)

    assert contingent_repository.is_liquidated_by_contingent("btc-1", Symbol.BTC)
    assert contingent_repository.is_liquidated_by_contingent("eth-1", Symbol.ETH)

    pending_infos = contingent_repository.get_pending_contingent_infos()
    assert len(pending_infos) == 1
    assert pending_infos[0].order_id == "eth-2"


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_delete_pending_contingent_info_with_multiple_symbols_and_sides(
    contingent_repository: ContingentInfoBaseRepository,
):
    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("btc-2", Symbol.BTC, PositionSide.short)
    contingent_repository.create_contingent_info("eth-1", Symbol.ETH, PositionSide.long)
    contingent_repository.create_contingent_info("eth-2", Symbol.ETH, PositionSide.short)

    contingent_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)
    contingent_repository.mark_contingent_info_as_triggered("eth-1", Symbol.ETH)

    contingent_repository.delete_pending_contingent_infos(Symbol.BTC, PositionSide.short)

    pending_infos = contingent_repository.get_pending_contingent_infos()
    assert len(pending_infos) == 1
    assert pending_infos[0].order_id == "eth-2"


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_delete_pending_contingent_info_with_sides(contingent_repository: ContingentInfoBaseRepository):
    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("btc-2", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("btc-3", Symbol.BTC, PositionSide.short)
    contingent_repository.create_contingent_info("btc-4", Symbol.BTC, PositionSide.short)

    contingent_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)
    contingent_repository.mark_contingent_info_as_triggered("eth-1", Symbol.ETH)

    contingent_repository.delete_pending_contingent_infos(Symbol.BTC, PositionSide.long)

    pending_infos = contingent_repository.get_pending_contingent_infos()
    assert len(pending_infos) == 2

    for info in pending_infos:
        assert info.side == PositionSide.short


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_mark_non_existent_contingent_info(contingent_repository: ContingentInfoBaseRepository):
    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)

    # the lines below has no effect
    contingent_repository.mark_contingent_info_as_triggered("eth-1", Symbol.ETH)
    contingent_repository.delete_pending_contingent_infos(Symbol.BTC, PositionSide.short)

    pending_infos = contingent_repository.get_pending_contingent_infos()
    assert len(pending_infos) == 1
    assert pending_infos[0].order_id == "btc-1"


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_is_liquidated_by_contingent(contingent_repository: ContingentInfoBaseRepository):
    order_id = "liquidation_test"
    symbol = Symbol.BTC
    contingent_repository.create_contingent_info(order_id, symbol, PositionSide.long)
    is_liquidated = contingent_repository.is_liquidated_by_contingent(order_id, symbol)
    assert is_liquidated is False

    contingent_repository.mark_contingent_info_as_triggered(order_id, symbol)
    is_liquidated = contingent_repository.is_liquidated_by_contingent(order_id, symbol)
    assert is_liquidated is True


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_is_liquidated_by_contingent_non_existent(contingent_repository: ContingentInfoBaseRepository):
    order_id = "liquidation_test"
    is_liquidated = contingent_repository.is_liquidated_by_contingent(order_id, Symbol.BTC)
    assert is_liquidated is False


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_get_pending_contingent_infos(contingent_repository: ContingentInfoBaseRepository):
    # Create two contingent info, one triggered and one pending
    contingent_repository.create_contingent_info("123", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("456", Symbol.ETH, PositionSide.long)
    contingent_repository.mark_contingent_info_as_triggered(order_id="123", symbol=Symbol.BTC)

    # Get pending contingent info
    pending_contingent_infos = contingent_repository.get_pending_contingent_infos()

    # Assert
    assert len(pending_contingent_infos) == 1
    assert pending_contingent_infos[0].order_id == "456"
