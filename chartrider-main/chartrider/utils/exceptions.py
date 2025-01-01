class ChartRiderError(Exception):
    def __init__(self, message=""):
        super().__init__(message)


class OutOfMoney(ChartRiderError):
    def __init__(self, message="Not enough money to buy the asset."):
        super().__init__(message)


class StakeCurrencyMismatch(ChartRiderError):
    def __init__(self, message="Stake currency should be the same as the quote currency."):
        super().__init__(message)


class NoOpenPosition(ChartRiderError):
    def __init__(self, message="There is no open position to close."):
        super().__init__(message)


class InvalidOrder(ChartRiderError):
    def __init__(self, message="Invalid order."):
        super().__init__(message)


class InvalidTrade(ChartRiderError):
    def __init__(self, message="Invalid trade."):
        super().__init__(message)


class TerminationSignalReceived(ChartRiderError):
    def __init__(self, message="Termination signal received."):
        super().__init__(message)
