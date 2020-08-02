from ccxt.base.errors import ExchangeError
from ccxt.base.errors import NetworkError
from ccxt.base.errors import DDoSProtection

error_hierarchy = {
    'BaseError': {
        'ExchangeError': {
            'SubscribeError': {},
            'UnsubscribeError': {},
        },
        'NetworkError': {
            'DDoSProtection': {
                'ChannelLimitExceeed': {},
            },
            'ExchangeNotAvailable': {
                'OnMaintenance': {},
            },
            'Reconnect': {},
            'UnkownResponse': {},
        }
    }
}


class SubscribeError(ExchangeError):
    pass


class UnsubscribeError(ExchangeError):
    pass


class ChannelLimitExceeded(DDoSProtection):
    pass


class Reconnect(NetworkError):
    pass


class UnknownResponse(NetworkError):
    pass
