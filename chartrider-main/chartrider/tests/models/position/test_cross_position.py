import pytest

from chartrider.core.common.repository.models import Position


def test_cross_position_maintenance_margin(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert pytest.approx(float(position.maintenanceMargin)) == ccxt_cross_position_data["maintenanceMargin"]


def test_cross_position_margin_ratio(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert pytest.approx(float(position.marginRatio), abs=1e-4) == ccxt_cross_position_data["marginRatio"]


def test_cross_position_isolated_margin(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert pytest.approx(float(position.isolatedMargin)) == 0


def test_cross_position_initial_margin(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert pytest.approx(float(position.initialMargin)) == ccxt_cross_position_data["initialMargin"]


def test_cross_position_maintenance_margin_rate(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert (
        pytest.approx(float(position.maintenanceMarginRate)) == ccxt_cross_position_data["maintenanceMarginPercentage"]
    )


def test_cross_position_maintenance_margin_amount(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert pytest.approx(float(position.maintenanceMargin)) == ccxt_cross_position_data["maintenanceMargin"]


def test_cross_position_collateral(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert pytest.approx(float(position.collateral)) == ccxt_cross_position_data["collateral"]


def test_cross_position_unrealized_pnl(ccxt_cross_position_data: dict):
    position = Position(**ccxt_cross_position_data)
    assert pytest.approx(float(position.unrealizedPnl)) == float(
        (ccxt_cross_position_data["info"]["unRealizedProfit"])
    )
