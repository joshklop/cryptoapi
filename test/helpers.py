from unittest.mock import MagicMock

BOOK_METADATA = {
    'timestamp': None,
    'datetime': None,
    'nonce': None
}

TEST_MARKET = {'percentage': True, 'tierBased': True, 'maker': 0.001, 'taker': 0.002, 'tiers': {'taker': [[0, 0.002], [500000, 0.002], [1000000, 0.002], [2500000, 0.002], [5000000, 0.002], [7500000, 0.002], [10000000, 0.0018], [15000000, 0.0016], [20000000, 0.0014000000000000002], [25000000, 0.0012], [30000000, 0.001]], 'maker': [[0, 0.001], [500000, 0.0008], [1000000, 0.0006], [2500000, 0.0004], [5000000, 0.0002], [7500000, 0], [10000000, 0], [15000000, 0], [20000000, 0], [25000000, 0], [30000000, 0]]}, 'precision': {'price': 5, 'amount': 8}, 'limits': {'amount': {'min': 0.0006, 'max': 2000.0}, 'price': {'min': 1e-05, 'max': 100000.0}, 'cost': {'min': 6e-09, 'max': None}}, 'id': 'BTCUSD', 'symbol': 'BTC/USD', 'base': 'BTC', 'quote': 'USD', 'baseId': 'BTC', 'quoteId': 'USD', 'active': True, 'info': {'pair': 'btcusd', 'price_precision': 5, 'initial_margin': '20.0', 'minimum_margin': '10.0', 'maximum_order_size': '2000.0', 'minimum_order_size': '0.0006', 'expiration': 'NA', 'margin': True}}

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


class AsyncContextManager(MagicMock):
    async def __aenter__(self, *args, **kwargs):
        return super().__enter__(*args, **kwargs)

    async def __aexit__(self, *args, **kwargs):
        return super().__exit__(*args, **kwargs)
