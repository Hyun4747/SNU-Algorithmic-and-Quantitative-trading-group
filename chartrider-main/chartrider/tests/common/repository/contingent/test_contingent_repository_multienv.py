import pytest

from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoBaseRepository,
)
from chartrider.core.common.repository.models import PositionSide
from chartrider.tests.common.repository.contingent.conftest import (
    ContingentRepositoryFactory,
)
from chartrider.utils.symbols import Symbol


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_trigger_contingent_info_with_multiple_user(
    contingent_repository: ContingentInfoBaseRepository,
    contingent_repository_factory: ContingentRepositoryFactory,
):
    another_repository = contingent_repository_factory.get_repository(
        user_id="another_user", testnet=False, base_repository=contingent_repository
    )

    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)
    another_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)

    contingent_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)
    assert not another_repository.is_liquidated_by_contingent("btc-1", Symbol.BTC)


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_trigger_contingent_info_with_different_network(
    contingent_repository: ContingentInfoBaseRepository,
    contingent_repository_factory: ContingentRepositoryFactory,
):
    another_repository = contingent_repository_factory.get_repository(
        user_id=contingent_repository.user_id, testnet=True, base_repository=contingent_repository
    )

    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)
    another_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)

    contingent_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)
    assert not another_repository.is_liquidated_by_contingent("btc-1", Symbol.BTC)


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_delete_pending_with_multiple_user(
    contingent_repository: ContingentInfoBaseRepository,
    contingent_repository_factory: ContingentRepositoryFactory,
):
    another_repository = contingent_repository_factory.get_repository(
        user_id="another_user", testnet=False, base_repository=contingent_repository
    )

    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("btc-2", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("eth-1", Symbol.ETH, PositionSide.long)
    contingent_repository.create_contingent_info("eth-2", Symbol.ETH, PositionSide.long)

    another_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)

    contingent_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)
    contingent_repository.delete_pending_contingent_infos(Symbol.BTC, PositionSide.long)
    assert len(contingent_repository.get_pending_contingent_infos()) == 2


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_get_pending_contingent_infos_different_user(
    contingent_repository: ContingentInfoBaseRepository,
    contingent_repository_factory: ContingentRepositoryFactory,
):
    another_repository = contingent_repository_factory.get_repository(
        user_id="another_user", testnet=False, base_repository=contingent_repository
    )
    another_repository.create_contingent_info("btc-1", Symbol.ETH, PositionSide.long)

    contingent_repository.create_contingent_info("btc-1", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("btc-2", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("eth-1", Symbol.ETH, PositionSide.long)
    contingent_repository.create_contingent_info("eth-2", Symbol.ETH, PositionSide.long)

    contingent_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)
    another_repository.mark_contingent_info_as_triggered("btc-1", Symbol.BTC)  # noop

    pending_infos = contingent_repository.get_pending_contingent_infos()
    assert len(pending_infos) == 3

    another_pending_infos = another_repository.get_pending_contingent_infos()
    assert len(another_pending_infos) == 1


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_same_order_id_with_different_symbol(contingent_repository: ContingentInfoBaseRepository):
    contingent_repository.create_contingent_info("same", Symbol.BTC, PositionSide.long)
    contingent_repository.create_contingent_info("same", Symbol.ETH, PositionSide.long)
    contingent_repository.create_contingent_info("eth-1", Symbol.ETH, PositionSide.long)

    contingent_repository.mark_contingent_info_as_triggered("same", Symbol.BTC)
    assert not contingent_repository.is_liquidated_by_contingent("same", Symbol.ETH)


@pytest.mark.parametrize(
    "contingent_repository",
    ["contingent_db_repository", "contingent_inmemory_repository"],
    indirect=True,
)
def test_cant_create_if_only_differs_side(contingent_repository: ContingentInfoBaseRepository):
    contingent_repository.create_contingent_info("same", Symbol.BTC, PositionSide.long)
    with pytest.raises(Exception):
        contingent_repository.create_contingent_info("same", Symbol.BTC, PositionSide.short)
