__version__ = '0.1.0'


from cryptoapi.base.exchange import Exchange

from cryptoapi.bitfinex import Bitfinex
from cryptoapi.bitvavo import Bitvavo
from cryptoapi.coinbasepro import Coinbasepro
from cryptoapi.kraken import Kraken

from cryptoapi.base import errors
from cryptoapi.base.errors import error_hierarchy
from cryptoapi.base.errors import SubscribeError
from cryptoapi.base.errors import UnsubscribeError
from cryptoapi.base.errors import ChannelLimitExceeded
from cryptoapi.base.errors import Reconnect
from cryptoapi.base.errors import UnknownResponse

exchanges = [
    'Bitfinex',
    'Bitvavo',
    'Coinbasepro',
    'Kraken'
]

base = [
    'Exchange',
    'exchanges',
]

__all__ = base + errors.__all__ + exchanges
