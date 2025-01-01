from __future__ import annotations

import random
import string
from enum import Enum, StrEnum, auto
from functools import cached_property
from typing import Annotated, Any, Literal, Self, TypeVar

from loguru import logger
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    FieldValidationInfo,
    field_validator,
    model_validator,
)

from chartrider.core.strategy.signpost import Signposter
from chartrider.utils.exceptions import InvalidOrder, InvalidTrade
from chartrider.utils.prettyprint import PrettyPrint, PrettyPrintMode
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import TimeUtils

# ----------------------------------- Enums ---------------------------------- #


class MarginMode(StrEnum):
    isolated = auto()
    cross = auto()

    @cached_property
    def isIsolated(self) -> bool:
        return self == MarginMode.isolated


class OrderStatus(StrEnum):
    open = "open"
    closed = "closed"
    canceled = "canceled"
    expired = "expired"
    rejected = "rejected"

    def __str__(self) -> str:
        return self.value.upper()


class OrderType(StrEnum):
    limit = "limit"
    market = "market"
    stop = "stop"
    stop_market = "stop_market"
    take_profit = "take_profit"
    take_profit_market = "take_profit_market"
    liquidation = "liquidation"  # forced liquidation
    # trailing_stop_market = "trailing_stop_market"  # not implemented

    def __str__(self) -> str:
        return self.value.upper()


class OrderSide(StrEnum):
    buy = "buy"
    sell = "sell"

    @property
    def isBuy(self) -> bool:
        return self == OrderSide.buy

    @property
    def isSell(self) -> bool:
        return self == OrderSide.sell

    @property
    def opposite(self) -> OrderSide:
        if self == OrderSide.buy:
            return OrderSide.sell
        return OrderSide.buy


class Timeframe(Enum):
    m1 = 1
    m3 = 3
    m5 = 5
    m15 = 15
    m30 = 30
    h1 = 60
    h2 = 120
    h4 = 240
    h6 = 360
    h8 = 480
    h12 = 720
    d1 = 1440
    d3 = 4320
    w1 = 10080
    M1 = 43200

    def __str__(self) -> str:
        return f"{self.value}m"

    @property
    def minutes(self) -> int:
        return self.value

    @property
    def milliseconds(self) -> int:
        return self.value * 60 * 1000


class TimeInForce(StrEnum):
    """
    - `GTC`: Good Till Cancelled. The order remains active until it is explicitly cancelled by the trader.
    - `GTE_GTC`: Good Till Expired or Cancelled. The order remains active until it is explicitly cancelled by the trader or until the order expires. Used or TL/SL orders.
    - `IOC`: Immediate or Cancel. The order is executed immediately, and any unfilled portion is cancelled.
    - `FOK`: Fill or Kill. The order must be filled immediately and completely, or it is cancelled.
    - `PO`: Post Only. The order is only posted to the order book and cannot be executed immediately. If the order cannot
      be posted to the book without taking liquidity, it is rejected.
    """  # noqa: E501

    GTC = "GTC"
    GTE_GTC = "GTE_GTC"
    IOC = "IOC"
    FOK = "FOK"
    PO = "PO"


class TakerOrMaker(StrEnum):
    taker = "taker"
    maker = "maker"


class PositionSide(StrEnum):
    long = "long"
    short = "short"

    def __init__(self, side: str) -> None:
        self.side = side.lower()

    def __str__(self) -> str:
        return self.side.upper()

    @property
    def isLong(self) -> bool:
        return self == PositionSide.long

    @property
    def isShort(self) -> bool:
        return self == PositionSide.short


class OrderAction(StrEnum):
    open_long = "open_long"
    open_short = "open_short"
    close_long = "close_long"
    close_short = "close_short"

    @staticmethod
    def from_side(order_side: OrderSide, position_side: PositionSide) -> OrderAction:
        if order_side == OrderSide.buy:
            return OrderAction.open_long if position_side == PositionSide.long else OrderAction.close_short
        else:
            return OrderAction.close_long if position_side == PositionSide.long else OrderAction.open_short

    @cached_property
    def orderSide(self) -> OrderSide:
        if self in (self.open_long, self.close_short):
            return OrderSide.buy
        else:
            return OrderSide.sell

    @cached_property
    def positionSide(self) -> PositionSide:
        if self in (self.open_long, self.close_long):
            return PositionSide.long
        else:
            return PositionSide.short

    @cached_property
    def isOpening(self) -> bool:
        return self in (self.open_long, self.open_short)

    @cached_property
    def isClosing(self) -> bool:
        return self in (self.close_long, self.close_short)

    def __str__(self) -> str:
        return self.value.upper()


# ---------------------------------- Models ---------------------------------- #


class Balance(BaseModel):
    info: dict[str, Any] | None = None

    totalWalletBalance: float
    totalUnrealizedProfit: float
    totalOpenOrderInitialMargin: float
    totalMaintMargin: float
    totalPositionInitialMargin: float
    """
    The sum of all cross positions' `initialMargin`.
    In real Binance API, isolated positions' `initialMargin` are also included to this field.
    """
    totalPositionIsolatedMargin: float = 0
    """
    The sum of all isolated positions' `isolatedMargin`. This field does not exist in real Binance API.
    This field is added to calculate the available balance with isolated positions.
    """

    @staticmethod
    def initial_balance(cash: int = 100000) -> Balance:
        return Balance(
            totalWalletBalance=cash,
            totalUnrealizedProfit=0,
            totalOpenOrderInitialMargin=0,
            totalMaintMargin=0,
            totalPositionInitialMargin=0,
            totalPositionIsolatedMargin=0,
        )

    @property
    def totalMarginBalance(self) -> float:
        return self.totalWalletBalance + self.totalUnrealizedProfit

    @property
    def availableBalance(self) -> float:
        if self.info is not None and (available_balance := self.info.get("availableBalance")):
            # return live server-side information if available
            return float(available_balance)
        return (
            self.totalMarginBalance
            - self.totalPositionInitialMargin
            - self.totalOpenOrderInitialMargin
            - self.totalPositionIsolatedMargin
        )

    def __str__(self) -> str:
        return f"Balance({', '.join([f'{k}={v}' for k, v in [*self.model_dump().items(), ('availableBalance', self.availableBalance), ('totalMarginBalance', self.totalMarginBalance)]])})"  # noqa: E501


class ClientOrderId(BaseModel):
    @staticmethod
    def slug_no_underscore(v: str | None) -> str | None:
        if v is not None and "_" in v:
            raise ValueError("strategy must not contain '_'")
        return v

    strategy: Annotated[str | None, BeforeValidator(slug_no_underscore)]
    timestamp: int
    identifier: str | None = None

    def encode(self) -> str | None:
        encoded = f"{self.strategy}_{self.timestamp}_{self.identifier}"
        if len(encoded) > 36:
            logger.warning(f"ClientOrderId {encoded} is too long. Using None instead.")
            return None
        return encoded

    @staticmethod
    def decode(id: ClientOrderId | str | None) -> ClientOrderId | None:
        if id is None:
            return None
        if isinstance(id, ClientOrderId):
            return id
        try:
            strategy, timestamp, identifier = id.split("_")
            if strategy == "None":
                strategy = None
            return ClientOrderId(strategy=strategy, timestamp=int(timestamp), identifier=identifier)
        except Exception as e:
            logger.warning(f"Failed to decode ClientOrderId {id}: {e}")
            return None

    @model_validator(mode="after")
    def auto_generate_identifier(self) -> Self:
        if self.identifier is None:
            self.identifier = self.generate_random_id()
        return self

    def generate_random_id(self) -> str:
        remaining_slots = 36 - len(self.strategy or "None") - len(str(self.timestamp)) - 2
        return "".join(random.choices(string.ascii_letters + string.digits, k=remaining_slots))

    def with_timestamp(self, timestamp: int) -> ClientOrderId:
        return ClientOrderId(strategy=self.strategy, timestamp=timestamp)


class Fee(BaseModel):
    currency: str
    cost: float
    rate: float | None = None


class ContingentOrder(BaseModel):
    triggerPrice: float
    price: float | None = None  # None for market order


class Order(BaseModel):
    id: str
    timestamp: int | None
    symbol: Annotated[Symbol, BeforeValidator(Symbol.decode)]
    price: float | None
    amount: float
    stopPrice: float | None
    status: OrderStatus
    type: OrderType
    side: OrderSide
    trades: list[Trade]
    filled: float
    timeInForce: TimeInForce
    clientOrderId: Annotated[ClientOrderId | None | str, BeforeValidator(ClientOrderId.decode)]
    info: dict[str, Any] | None = None

    signposter: Signposter | None = None
    """An optional signposter for plotting & debugging purposes."""

    model_config = ConfigDict(
        ignored_types=(cached_property,),
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    def validated(self) -> Self:
        try:
            return _validate(self)
        except Exception as e:
            raise InvalidOrder(str(e))

    @cached_property
    def orderAction(self) -> OrderAction:
        if self.positionSide == PositionSide.long:
            if self.side == OrderSide.buy:
                return OrderAction.open_long
            else:
                return OrderAction.close_long
        else:
            if self.side == OrderSide.buy:
                return OrderAction.close_short
            else:
                return OrderAction.open_short

    @property
    def positionSide(self) -> PositionSide:
        position_side = self.info.get("positionSide") or self.info.get("ps", "") if self.info else None
        if not position_side:
            raise ValueError("Position side not found in order info")
        return PositionSide(position_side.lower())

    @positionSide.setter
    def positionSide(self, value: PositionSide):
        self.info = self.info or {}
        self.info["positionSide"] = str(value)

    @property
    def cost(self) -> float | None:
        """Total cost of the order, including fees."""
        if self.price is None:
            # it's market order and we don't know the price yet
            return None
        return self.amount * self.price

    @property
    def remaining(self) -> float:
        """Amount of the order that is still open."""
        return self.amount - self.filled

    @property
    def average(self) -> float:
        """Average filled price of each trade."""
        if len(self.trades) == 0:
            return 0
        return sum([t.price for t in self.trades]) / float(len(self.trades))

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.id == other.id

    def format(self, html: bool = False) -> str:
        mode = PrettyPrintMode.light_html if html else PrettyPrintMode.terminal
        pp = PrettyPrint(mode=mode)
        pp.subheader(f"Order {self.id}")
        pp.key_value("Symbol", self.symbol)
        pp.key_value("Price [$]", self.price)
        pp.key_value("Amount", self.amount)
        pp.key_value("Cost [$]", self.cost)
        pp.key_value("Action", self.orderAction, force_color="green" if self.side.isBuy else "red")
        pp.key_value("Status", self.status)
        pp.key_value("Type", self.type)
        if self.timestamp:
            pp.key_value("Timestamp", TimeUtils.timestamp_to_datestring(self.timestamp))
        return pp.result


class Trade(BaseModel):
    id: str
    timestamp: int
    symbol: Annotated[Symbol, BeforeValidator(Symbol.decode)]
    order: str | None
    side: OrderSide
    takerOrMaker: TakerOrMaker
    price: float
    amount: float
    fee: Fee
    realizedPnl: float = 0
    realizedPnlPercent: float = 0.0  # for backtesting-only
    info: dict[str, Any] | None = None

    @property
    def notional(self) -> float:
        """The value of the trade in the quote currency."""
        return self.price * self.amount

    def validated(self) -> Self:
        try:
            return _validate(self)
        except Exception as e:
            raise InvalidTrade(str(e))


class OrderBook(BaseModel):
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    symbol: Annotated[Symbol, BeforeValidator(Symbol.decode)]
    timestamp: int | None
    datetime: str | None
    nonce: int


class OrderRequestParams(BaseModel):
    @staticmethod
    def encode_client_order_id(v) -> str | None:
        if isinstance(v, ClientOrderId):
            return v.encode()
        return v

    timeInForce: str | None = None
    stopPrice: float | None = None
    positionSide: PositionSide | None = None
    closePosition: bool | None = None
    clientOrderId: Annotated[ClientOrderId | None | str, BeforeValidator(encode_client_order_id)] = None

    model_config = ConfigDict(validate_assignment=True)


class Position(BaseModel):
    info: dict[str, Any] | None = None
    symbol: Annotated[Symbol, BeforeValidator(Symbol.decode)]
    timestamp: int
    hedged: bool
    side: PositionSide
    contracts: float  # the amount of open position in absolute value
    entryPrice: float
    markPrice: float  # during backtesting, this value gets updated with each candle
    leverage: int
    marginMode: MarginMode
    isolatedWallet: float = 0
    """
    Isolated wallet for the position. This value is meaningful only when marginMode is "isolated".
    This is the amount of margin that is locked for the entire lifecycle of the position.
    This value is referred to as "Margin" on Binance Futures Web UI, in "isolated" mode.

    ```
    Isolated Wallet = Entry Margin + Open Loss - Trading Fee
                    = (Entry Price * Contracts) / Leverage + Open Loss - Trading Fee
    ```

    where,

    ```
    Open Loss       = Contracts * abs(min(0, Direction * (Mark Price - Entry Price)))
    Entry Price     = Assuming Price (if market order)
                    = Order Price    (if limit order)
    Assuming Price  = ask[0] * (1 + 0.05%) (if long order)
                    = bid[0] (if short order)
    ```

    For backtesting, as we don't have access to the mark price or orderbook data,
    we assume `last price == mark price == entry price`, hence the open loss is always 0.
    """

    # for backtesting
    closedTimestamp: int | None = None
    openedAmount: float | None = None  # cumulative
    averageOpenPrice: float | None = None  # cumulative
    closedAmount: float = float(0)  # cumulative
    averageClosePrice: float | None = None  # cumulative

    model_config = ConfigDict(validate_default=True)

    @field_validator("isolatedWallet", mode="before")
    def set_isolated_wallet(cls, v, info: FieldValidationInfo):
        if info.data["marginMode"] == MarginMode.cross:
            return 0
        if (info_dict := info.data.get("info")) is not None and (value := info_dict.get("isolatedWallet")) is not None:
            return float(value)
        if isinstance(v, float):
            return v
        raise ValueError("isolatedWallet is required")

    @model_validator(mode="after")
    def isolated_wallet_should_be_none_in_cross_mode(self) -> Self:
        if self.marginMode == MarginMode.cross and not (self.isolatedWallet is None or self.isolatedWallet == 0):
            raise ValueError("isolatedWallet should be None or 0 in cross mode")
        return self

    @field_validator("side", mode="before")
    def set_side(cls, v, info: FieldValidationInfo):
        if v is None and (raw_side := info.data.get("info", {}).get("positionSide")) is not None:
            return PositionSide(raw_side.lower())
        return v

    @property
    def isolatedMargin(self) -> float:
        if self.marginMode == MarginMode.cross:
            return 0
        if self.isolatedWallet is None:
            raise ValueError("isolatedWallet is required")
        return self.isolatedWallet + self.unrealizedPnl

    @property
    def collateral(self) -> float:
        if self.marginMode == MarginMode.isolated:
            return self.isolatedMargin
        sign = 1 if self.side == PositionSide.short else -1
        one_plus_mmp = float("1") * sign + self.maintenanceMarginRate
        entry_price = self.entryPrice * (-sign)
        return (self.liquidationPrice * one_plus_mmp + entry_price) * self.contracts

    @property
    def liquidationPrice(self) -> float:
        """See https://www.binance.com/en/support/faq/how-to-calculate-liquidation-price-of-usd%E2%93%A2-m-futures-contracts-b3c689c1f50a44cabb3a84e663b81d93"""
        if self.info is not None and (liq_price := self.info.get("liquidationPrice", None)) is not None:
            # return server-side liquidation price if available
            return float(str(liq_price))
        if self.marginMode == MarginMode.cross:
            raise NotImplementedError("Calculation of liquidation price in cross mode is not supported.")
        if self.isolatedWallet is None:
            raise ValueError("isolatedWallet is required")
        sign = 1 if self.side == PositionSide.short else -1
        return (self.isolatedWallet + self.maintenanceAmount + sign * self.contracts * self.entryPrice) / (
            self.contracts * self.maintenanceMarginRate + sign * self.contracts
        )

    @property
    def marginRatio(self) -> float:
        return self.maintenanceMargin / self.collateral

    @property
    def notional(self) -> float:
        return self.contracts * self.markPrice

    @property
    def initialMargin(self) -> float:
        return self.notional / self.leverage

    @property
    def unrealizedPnl(self) -> float:
        pnl = (self.markPrice - self.entryPrice) * self.contracts
        return pnl if self.side == PositionSide.long else -pnl

    @property
    def percentage(self) -> float:
        entry_cost = self.entryPrice * self.contracts / self.leverage
        return (self.unrealizedPnl / entry_cost) * 100

    @property
    def maintenanceMargin(self) -> float:
        return self.notional * self.maintenanceMarginRate - self.maintenanceAmount

    @property
    def maintenanceMarginRate(self) -> float:
        info = MarginInfo.calculate_margin_info(position_amount=self.contracts)
        return info.maintenance_margin_rate

    @property
    def maintenanceAmount(self) -> float:
        info = MarginInfo.calculate_margin_info(position_amount=self.contracts)
        return info.maintenance_amount

    @property
    def realizedPnl(self) -> float:
        assert self.closedAmount == self.openedAmount
        if self.averageClosePrice is None or self.averageOpenPrice is None:
            return float(0)
        pnl = (self.averageClosePrice - self.averageOpenPrice) * self.closedAmount
        return pnl if self.side == PositionSide.long else -pnl

    def format(self, html: bool = False) -> str:
        mode = PrettyPrintMode.light_html if html else PrettyPrintMode.terminal
        pp = PrettyPrint(mode=mode)
        pp.subheader(f"Position {self.symbol}")
        pp.key_value("Side", self.side, force_color="green" if self.side == PositionSide.long else "red")
        pp.key_value("Amount", self.contracts)
        pp.key_value("Entry Price [$]", self.entryPrice, decimal_places=8)
        pp.key_value("Mark Price [$]", self.markPrice, decimal_places=8)
        pp.key_value("Unrealized PnL [$]", self.unrealizedPnl, colorize=True, decimal_places=3)
        pp.key_value("Percentage [%]", self.percentage, colorize=True, decimal_places=3)
        return pp.result


class MarketPrecision(BaseModel):
    price: int
    amount: int
    base: int
    quote: int


class MarketLimit(BaseModel):
    min: float | None
    max: float | None


class MarketLimits(BaseModel):
    amount: MarketLimit
    price: MarketLimit
    cost: MarketLimit
    leverage: MarketLimit
    market: MarketLimit | None


class Market(BaseModel):
    id: str
    symbol: Annotated[Symbol, BeforeValidator(Symbol.decode)]
    base: str
    quote: str
    baseId: str
    quoteId: str
    active: bool
    precision: MarketPrecision
    limits: MarketLimits
    contract: bool
    contractSize: float | None
    settle: str
    settleId: str

    taker: float
    maker: float

    type: Literal["spot", "future", "swap"]  # "swap" is for perpetual futures
    info: dict[str, Any] | None = None


class MarginInfo(BaseModel):
    max_leverage: int
    maintenance_margin_rate: float
    maintenance_amount: float

    @staticmethod
    def calculate_margin_info(position_amount: float) -> MarginInfo:
        """See https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin"""
        brackets = [
            (50000, 125, 0.004, 0),
            (250000, 100, 0.005, 50),
            (3000000, 50, 0.01, 1300),
            (15000000, 20, 0.025, 46300),
            (30000000, 10, 0.05, 421300),
            (80000000, 5, 0.1, 1921300),
            (100000000, 4, 0.125, 3921300),
            (200000000, 3, 0.15, 6421300),
            (300000000, 2, 0.25, 26421300),
            (500000000, 1, 0.5, 101421300),
        ]

        for limit, max_leverage, maintenance_margin_rate, maintenance_amount in brackets:
            if position_amount < limit:
                return MarginInfo(
                    max_leverage=max_leverage,
                    maintenance_margin_rate=maintenance_margin_rate,
                    maintenance_amount=maintenance_amount,
                )
        raise ValueError("Position amount is out of range.")


T = TypeVar("T", Order, Trade)


def _validate(self: T) -> T:
    from chartrider.utils.exchange import ExchangeFactory

    market = ExchangeFactory.get_market(self.symbol)

    self.amount = ExchangeFactory.amount_to_precision(self.symbol, self.amount)
    if self.price is not None:
        self.price = ExchangeFactory.price_to_precision(self.symbol, self.price)

    if isinstance(self, Trade):
        return self

    if (min_amount := market.limits.amount.min) is not None:
        assert self.amount >= min_amount, f"{self.amount} < {min_amount}"
    if (max_amount := market.limits.amount.max) is not None:
        assert self.amount <= max_amount, f"{self.amount} > {max_amount}"

    if self.orderAction.isClosing or self.price is None:
        return self

    # Only opening limit orders have limitation on price and notional value
    if (min_price := market.limits.price.min) is not None:
        assert self.price >= min_price, f"{self.price} < {min_price}"
    if (max_price := market.limits.price.max) is not None:
        assert self.price <= max_price, f"{self.price} > {max_price}"
    if (min_cost := market.limits.cost.min) is not None:
        assert self.amount * self.price >= min_cost, f"{self.amount} * {self.price} < {min_cost}"
    if (max_cost := market.limits.cost.max) is not None:
        assert self.amount * self.price <= max_cost, f"{self.amount} * {self.price} > {max_cost}"
    return self


Order.model_rebuild()
