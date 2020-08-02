import unittest
from cryptoapi.bitvavo import Bitvavo
from test.helpers import AsyncContextManager, BOOK_METADATA

TEST_MARKET = {
    'percentage': True,
    'tierBased': True,
    'taker': 0.0025,
    'maker': 0.002,
    'tiers': {
        'taker': [
            [0, 0.0025],
            [50000, 0.0024],
            [100000, 0.0022],
            [250000, 0.002],
            [500000, 0.0018],
            [1000000, 0.0016],
            [2500000, 0.0014],
            [5000000, 0.0012],
            [10000000, 0.001]
        ],
        'maker': [
            [0, 0.002],
            [50000, 0.0015],
            [100000, 0.001],
            [250000, 0.0006],
            [500000, 0.0003],
            [1000000, 0.0001],
            [2500000, -0.0001],
            [5000000, -0.0003],
            [10000000, -0.0005]
        ]
    },
    'precision': {
        'price': 5,
        'amount': 8
    },
    'limits': {
        'amount': {
            'min': 0.001,
            'max': None
        },
        'price': {
            'min': None,
            'max': None
        },
        'cost': {
            'min': 5.0,
            'max': None
        }
    },
    'id': 'BTC-EUR',
    'symbol': 'BTC/EUR',
    'base': 'BTC',
    'quote': 'EUR',
    'baseId': 'BTC',
    'quoteId': 'EUR',
    'info': {
        'market': 'BTC-EUR',
        'status': 'trading',
        'base': 'BTC',
        'quote': 'EUR',
        'pricePrecision': 5,
        'minOrderInBaseAsset': '0.001',
        'minOrderInQuoteAsset': '5',
        'orderTypes': ['market', 'limit']
    },
    'active': True
}


class TestBitvavo(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with Bitvavo():
            self.exchange = Bitvavo()
            symbol = TEST_MARKET['symbol']
            self.exchange.markets = {symbol: TEST_MARKET}
            self.exchange.markets_by_id = {TEST_MARKET['id']: TEST_MARKET}
            self.test_market = self.exchange.markets[symbol]

    def test_build_requests(self):
        symbols = [self.test_market['symbol']]
        # All channel subscriptions are the same, we just arbitrarily
        # chose to use the TICKER channel.
        name = self.exchange.TICKER
        ex_name = self.exchange.channels[name]['ex_name']

        requests = self.exchange.build_requests(symbols, name)

        correct_requests = [
            {
                'action': 'subscribe',
                'channels': [{'name': ex_name, 'markets': [self.test_market['id']]}]}
        ]
        self.assertEqual(correct_requests, requests)

    def test_ex_channel_id_from_reply(self):
        reply = {
            'event': self.exchange.TICKER,
            'market': self.test_market['id']
        }

        self.assertEqual(
            (reply['event'], reply['market']),
            self.exchange.ex_channel_id_from_reply(reply)
        )

    def test_register_channel(self):
        """Ticker, trades, order_book"""
        name = self.exchange.TICKER
        ex_name = self.exchange.channels[name]['ex_name']
        id = self.test_market['id']
        reply = {
            'event': 'subscribed',
            'subscriptions': {ex_name: [id]}
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_registration = {
            'request': {
                'action': 'subscribe',
                'channels': [{'name': ex_name, 'markets': [id]}],
            },
            'channel_id': 0,
            'ex_channel_id': (ex_name, id),
            'name': name,
            'symbol': self.test_market['symbol']
        }
        self.assertEqual([correct_registration], self.exchange.connections[websocket_mock])

    def test_register_ohlcvs_channel(self):
        """OHLCVS only"""
        name = self.exchange.OHLCVS
        ex_name = self.exchange.channels[name]['ex_name']
        id = self.test_market['id']
        timeframe = '1m'
        ex_timeframe = self.exchange.timeframes[timeframe]
        reply = {
            'event': 'subscribed',
            'subscriptions': {ex_name: {ex_timeframe: [id]}}
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_registration = {
            'request': {
                'action': 'subscribe',
                'channels': [{'name': ex_name, 'markets': [id], 'interval': ex_timeframe}],
            },
            'channel_id': 0,
            'ex_channel_id': (ex_name, id),
            'name': name,
            'symbol': self.test_market['symbol'],
            'timeframe': timeframe
        }
        self.assertEqual([correct_registration], self.exchange.connections[websocket_mock])

    def test_parse_order_book_ccxt_style(self):
        # Even though we are assuming this is a snapshot, it has no effect on
        # the internal logic.
        reply = {
            "event": self.exchange.channels[self.exchange.ORDER_BOOK]['ex_name'],
            "market": self.test_market['id'],
            "nonce": 0,
            "bids": [["10101.10", "0.45054140"]],
            "asks": [["10102.55", "0.57753524"]]
        }

        channel, update = self.exchange.parse_order_book_ws(reply, self.test_market)
        update.update(BOOK_METADATA)

        correct_book = {
            'bids': [[10101.10, 0.45054140]],
            'asks': [[10102.55, 0.57753524]],
            **BOOK_METADATA
        }
        symbol = self.test_market['symbol']
        self.assertEqual(correct_book, update[symbol])
