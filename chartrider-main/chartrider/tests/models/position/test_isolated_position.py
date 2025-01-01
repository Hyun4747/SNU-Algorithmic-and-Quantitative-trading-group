import pytest

from chartrider.core.common.repository.models import MarginMode, Position


def test_set_isolated_wallet(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    assert position.isolatedWallet == float(ccxt_isolated_position_data["info"]["isolatedWallet"])


def test_set_isolated_wallet_in_cross_mode(ccxt_isolated_position_data: dict):
    data = ccxt_isolated_position_data.copy()
    data["marginMode"] = MarginMode.cross
    position = Position(**data)
    assert position.isolatedWallet == 0


def test_set_isolated_wallet_prioritize_info(ccxt_isolated_position_data: dict):
    data = ccxt_isolated_position_data.copy()
    data["isolatedWallet"] = "100"
    position = Position(**data)
    assert position.isolatedWallet == float(ccxt_isolated_position_data["info"]["isolatedWallet"])


def test_set_isolated_wallet_info_changed(ccxt_isolated_position_data: dict):
    data = ccxt_isolated_position_data.copy()
    position = Position(**data)
    assert position.info is not None
    position.info["isolatedWallet"] = "100"

    # Does not react to info changes
    assert position.isolatedWallet == float(ccxt_isolated_position_data["info"]["isolatedWallet"])


def test_set_isolated_wallet_value_changed(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    position.isolatedWallet = 100
    assert position.isolatedWallet == 100


def test_isolated_position_maintenance_margin(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    assert pytest.approx(position.maintenanceMargin) == ccxt_isolated_position_data["maintenanceMargin"]


def test_isolated_position_margin_ratio(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    assert pytest.approx(position.marginRatio, abs=1e-4) == ccxt_isolated_position_data["marginRatio"]


def test_isolated_position_collateral(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    assert pytest.approx(position.collateral) == ccxt_isolated_position_data["collateral"]


def test_isolated_position_isolated_margin(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    assert pytest.approx(position.isolatedMargin, abs=1e-7) == float(
        ccxt_isolated_position_data["info"]["isolatedMargin"]
    )


def test_isolated_position_unrealized_pnl(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    assert pytest.approx(float(position.unrealizedPnl)) == float(
        ccxt_isolated_position_data["info"]["unRealizedProfit"]
    )


def test_isolated_position_margin_mode(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    assert position.marginMode == MarginMode.isolated
    assert position.marginMode == MarginMode.isolated.value
    assert position.marginMode == "isolated"


def test_isolated_position_liquidation_price(ccxt_isolated_position_data: dict):
    position = Position(**ccxt_isolated_position_data)
    if position.info is not None:
        # Remove from info to trigger manual calculation
        del position.info["liquidationPrice"]
    assert pytest.approx(float(position.liquidationPrice)) == ccxt_isolated_position_data["liquidationPrice"]


def test_isolated_position_margin_ratio_hit_100(ccxt_isolated_position_data: dict):
    data = ccxt_isolated_position_data.copy()
    position = Position(**data)
    liquidation_price = position.liquidationPrice

    # The current mark price hit the liquidation price
    position.markPrice = liquidation_price

    # This means the margin ratio became 100%
    assert pytest.approx(float(position.marginRatio)) == 1
