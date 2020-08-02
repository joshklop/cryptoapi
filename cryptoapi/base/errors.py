from ccxt import errors
from ccxt.base.errors import ExchangeError
from ccxt.base.errors import NetworkError
from ccxt.base.errors import DDoSProtection


cryptoapi_errors = [
    'error_hierarchy',
    'SubscribeError',
    'UnsubscribeError',
    'ChannelLimitExceeed',
    'Reconnect',
    'UnkownResponse'
]

# Do not include ccxt.error_hierarchy
__all__ = errors.__all__[1:] + cryptoapi_errors

error_hierarchy = {
    'BaseError': {
        'ExchangeError': {
            'AuthenticationError': {
                'PermissionDenied': {},
                'AccountSuspended': {},
            },
            'ArgumentsRequired': {},
            'BadRequest': {
                'BadSymbol': {},
            },
            'BadResponse': {
                'NullResponse': {},
            },
            'InsufficientFunds': {},
            'InvalidAddress': {
                'AddressPending': {},
            },
            'InvalidOrder': {
                'OrderNotFound': {},
                'OrderNotCached': {},
                'CancelPending': {},
                'OrderImmediatelyFillable': {},
                'OrderNotFillable': {},
                'DuplicateOrderId': {},
            },
            'NotSupported': {},
            'SubscribeError': {},
            'UnsubscribeError': {},
        },
        'NetworkError': {
            'DDoSProtection': {
                'RateLimitExceeded': {},
                'ChannelLimitExceeed': {},
            },
            'ExchangeNotAvailable': {
                'OnMaintenance': {},
            },
            'InvalidNonce': {},
            'RequestTimeout': {},
            'Reconnect': {},
            'UnkownResponse': {},
        },
    },
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
