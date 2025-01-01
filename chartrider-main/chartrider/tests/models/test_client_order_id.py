import pytest
from pydantic import ValidationError

from chartrider.core.common.repository.models import (
    ClientOrderId,
    Order,
    OrderRequestParams,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from chartrider.utils.symbols import Symbol


def test_from_id():
    raw_id = "vb03_12345_abc"
    client_order_id = ClientOrderId.decode(raw_id)
    assert client_order_id is not None
    assert client_order_id.strategy == "vb03"
    assert client_order_id.timestamp == 12345
    assert client_order_id.identifier == "abc"
    assert client_order_id.encode() == raw_id


def test_with_timestamp():
    client_order_id = ClientOrderId(strategy="vb03", timestamp=12345)
    new_client_order_id = client_order_id.with_timestamp(67890)
    assert new_client_order_id is not None
    assert new_client_order_id.strategy == "vb03"
    assert new_client_order_id.timestamp == 67890


def test_invalid_strategy():
    with pytest.raises(ValidationError):
        ClientOrderId(strategy="vb_03", timestamp=12345)


def test_invalid_from_id():
    assert ClientOrderId.decode("vb03_12345_67890_2323") is None


def test_invalid_from_id2():
    assert ClientOrderId.decode("vb03_12345") is None


def test_order_invalid_client_id():
    raw_id = "vb04_12345"
    order = Order(
        id="12345",
        timestamp=None,
        symbol=Symbol.BTC,
        price=None,
        amount=0,
        stopPrice=None,
        status=OrderStatus.open,
        type=OrderType.stop,
        side=OrderSide.buy,
        trades=[],
        filled=0,
        clientOrderId=raw_id,
        timeInForce=TimeInForce.GTC,
    )
    assert order.clientOrderId is None
    assert order.clientOrderId == ClientOrderId.decode(raw_id)


def test_order_valid_client_id():
    raw_id = "vb04_123_45"
    order = Order(
        id="12345",
        timestamp=None,
        symbol=Symbol.BTC,
        price=None,
        amount=0,
        stopPrice=None,
        status=OrderStatus.open,
        type=OrderType.stop,
        side=OrderSide.buy,
        trades=[],
        filled=0,
        clientOrderId=raw_id,
        timeInForce=TimeInForce.GTC,
    )
    assert isinstance(order.clientOrderId, ClientOrderId)
    assert order.clientOrderId == ClientOrderId.decode(raw_id)
    assert order.clientOrderId.identifier == "45"


def test_order_valid_client_id_to_invalid():
    raw_id = "vb04_12345_abc"
    order = Order(
        id="12345",
        timestamp=None,
        symbol=Symbol.BTC,
        price=None,
        amount=0,
        stopPrice=None,
        status=OrderStatus.open,
        type=OrderType.stop,
        side=OrderSide.buy,
        trades=[],
        filled=0,
        clientOrderId=raw_id,
        timeInForce=TimeInForce.GTC,
    )
    order.clientOrderId = "vb04_123_abc_db"
    assert order.clientOrderId is None


def test_order_invalid_client_id_to_valid():
    raw_id = "vb04_123_45_abc"
    order = Order(
        id="12345",
        timestamp=None,
        symbol=Symbol.BTC,
        price=None,
        amount=0,
        stopPrice=None,
        status=OrderStatus.open,
        type=OrderType.stop,
        side=OrderSide.buy,
        trades=[],
        filled=0,
        clientOrderId=raw_id,
        timeInForce=TimeInForce.GTC,
    )
    order.clientOrderId = "vb04_12345_abc"
    assert isinstance(order.clientOrderId, ClientOrderId)
    assert order.clientOrderId.strategy == "vb04"
    assert order.clientOrderId.timestamp == 12345
    assert order.clientOrderId.identifier == "abc"


def test_invalid_client_order_id_in_order_request_params():
    raw_id = "vb04_12345"
    client_order_id = ClientOrderId.decode(raw_id)
    params = OrderRequestParams()
    params.clientOrderId = client_order_id
    params_dict = params.model_dump()
    assert params_dict.get("clientOrderId") is None


def test_client_order_id_in_order_request_params():
    raw_id = "vb04_12345_abc"
    client_order_id = ClientOrderId.decode(raw_id)
    params = OrderRequestParams()
    params.clientOrderId = client_order_id
    params_dict = params.model_dump()
    assert params_dict.get("clientOrderId") == raw_id


def test_client_order_id_from_id_with_none_strategy():
    raw_id = "None_12345_abc"
    client_order_id = ClientOrderId.decode(raw_id)
    assert client_order_id and client_order_id.strategy is None


def test_client_order_id_autogenerate_identifier():
    client_order_id = ClientOrderId(strategy="vb03", timestamp=12345)
    assert client_order_id.identifier is not None
    encoded = client_order_id.encode()
    assert encoded is not None
    assert encoded == "vb03_12345_" + client_order_id.identifier
    assert len(encoded) == 36


def test_client_order_id_compare():
    client_order_id1 = ClientOrderId(strategy="vb03", timestamp=12345)
    client_order_id2 = ClientOrderId(strategy="vb03", timestamp=12345)
    assert client_order_id1 != client_order_id2


def test_client_order_id_identifier_preserved():
    client_order_id = ClientOrderId(strategy="vb03", timestamp=12345)
    encoded = client_order_id.encode()
    assert encoded is not None
    decoded = ClientOrderId.decode(encoded)
    assert decoded is not None
    assert client_order_id == decoded
