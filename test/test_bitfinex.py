import unittest
from cryptoapi.bitfinex import Bitfinex
from cryptoapi.errors import UnknownResponse
from test.helpers import AsyncContextManager, BOOK_METADATA

SYMBOL = 'BTC/USD'
ID = 'BTCUSD'
TEST_MARKET = {
    'percentage': True,
    'tierBased': True,
    'maker': 0.001,
    'taker': 0.002,
    'tiers': {
        'taker': [
            [0, 0.002],
            [500000, 0.002],
            [1000000, 0.002],
            [2500000, 0.002],
            [5000000, 0.002],
            [7500000, 0.002],
            [10000000, 0.0018],
            [15000000, 0.0016],
            [20000000, 0.0014000000000000002],
            [25000000, 0.0012],
            [30000000, 0.001]
        ],
        'maker': [
            [0, 0.001],
            [500000, 0.0008],
            [1000000, 0.0006],
            [2500000, 0.0004],
            [5000000, 0.0002],
            [7500000, 0],
            [10000000, 0],
            [15000000, 0],
            [20000000, 0],
            [25000000, 0],
            [30000000, 0]
        ]
    },
    'precision': {
        'price': 5,
        'amount': 8
    },
    'limits': {
        'amount': {
            'min': 0.0006,
            'max': 2000.0
        },
        'price': {
            'min': 1e-05,
            'max': 100000.0
        },
        'cost': {
            'min': 6e-09,
            'max': None
        }
    },
    'id': 'BTCUSD',
    'symbol': 'BTC/USD',
    'base': 'BTC',
    'quote': 'USD',
    'baseId': 'BTC',
    'quoteId': 'USD',
    'active': True,
    'info': {
        'pair': 'btcusd',
        'price_precision': 5,
        'initial_margin': '20.0',
        'minimum_margin': '10.0',
        'maximum_order_size': '2000.0',
        'minimum_order_size': '0.0006',
        'expiration': 'NA',
        'margin': True
    }
}


class TestBitfinex(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with Bitfinex():
            self.exchange = Bitfinex()
            self.exchange.markets = {SYMBOL: TEST_MARKET}
            self.exchange.markets_by_id = {ID: TEST_MARKET}
            self.test_market = TEST_MARKET

    def test_build_requests(self):
        symbols = [self.test_market['symbol']]
        name = self.exchange.TICKER

        requests = self.exchange.build_requests(symbols, name)

        correct_requests = [{
            'event': 'subscribe',
            'channel': 'ticker',
            'symbol': self.test_market['id']
        }]
        self.assertEqual(correct_requests, requests)

    def test_ex_channel_id_from_reply(self):
        dict_reply = {
            'chanId': 0
        }
        list_reply = [
            0,
            [
                123,
                456
            ]
        ]
        unknown_reply = 1

        self.assertEqual(0, self.exchange.ex_channel_id_from_reply(dict_reply))
        self.assertEqual(0, self.exchange.ex_channel_id_from_reply(list_reply))
        self.assertRaises(UnknownResponse, self.exchange.ex_channel_id_from_reply, unknown_reply)

    def test_register_ticker_or_trades_channel(self):
        """This stands for both ticker and trades because they're formatted the same"""
        channel = self.exchange.channels[self.exchange.TICKER]
        ex_name = channel['ex_name']
        ex_channel_id = 0
        id = self.test_market['id']
        reply = {
            "event": "subscribed",
            "channel": ex_name,
            "chanId": ex_channel_id,
            "symbol": id,
            "pair": id[1:]  # Remove the preceding `t`
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_registration = {
            'request': {
                'event': 'subscribe',
                'channel': ex_name,
                'symbol': id
            },
            # We know the first channel id is always 0.
            # See exchange.Exchange.claim_channel_id() for implementation.
            'channel_id': 0,
            'ex_channel_id': ex_channel_id,
            'name': self.exchange.TICKER,
            'symbol': self.test_market['symbol']
        }
        self.assertEqual([correct_registration], self.exchange.connections[websocket_mock])

    def test_register_order_book_channel(self):
        channel = self.exchange.channels[self.exchange.ORDER_BOOK]
        ex_name = channel['ex_name']
        ex_channel_id = 0
        id = self.test_market['id']
        depth = 100
        reply = {
            "event": "subscribed",
            "channel": ex_name,
            "chanId": ex_channel_id,
            "symbol": id,
            "prec": "P0",
            "freq": "F0",
            "len": depth
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_channel = {
            'request': {
                'event': 'subscribe',
                'channel': ex_name,
                'symbol': id,
                # These values are hardcoded in Bitfinex.subscribe_order_book
                "prec": "P0",
                "freq": "F0",
                "len": depth
            },
            # We know the first channel id is always 0.
            # See exchange.Exchange.claim_channel_id() for implementation.
            'channel_id': 0,
            'ex_channel_id': ex_channel_id,
            'name': self.exchange.ORDER_BOOK,
            'symbol': self.test_market['symbol'],
        }
        self.assertEqual([correct_channel], self.exchange.connections[websocket_mock])

    def test_register_ohlcvs_channel(self):
        channel = self.exchange.channels[self.exchange.OHLCVS]
        ex_name = channel['ex_name']
        ex_channel_id = 0
        id = self.test_market['id']
        timeframe = '1m'
        ex_timeframe = self.exchange.timeframes[timeframe]
        key = f'trade:{ex_timeframe}:{id}'
        reply = {
            "event": "subscribed",
            "channel": ex_name,
            "chanId": ex_channel_id,
            "key": key
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_channel = {
            'request': {
                'event': 'subscribe',
                'channel': ex_name,
                'key': key
            },
            # We know the first channel id is always 0.
            # See exchange.Exchange.claim_channel_id() for implementation.
            'channel_id': 0,
            'ex_channel_id': ex_channel_id,
            'name': self.exchange.OHLCVS,
            'symbol': self.test_market['symbol'],
            'timeframe': timeframe
        }
        self.assertEqual([correct_channel], self.exchange.connections[websocket_mock])

    def test_parse_order_book_snapshot_ccxt_style(self):
        reply = [17082, [[7254.7, 3, 3.3]]]

        channel, update = self.exchange.parse_order_book_ws(reply, self.test_market)
        symbol = self.test_market['symbol']
        update[symbol].update(BOOK_METADATA)

        correct_book = {
            'bids': [[7254.7, 3.3]],
            'asks': [],
            **BOOK_METADATA
        }
        self.assertEqual(correct_book, update[symbol])

    def test_parse_order_book_update_ccxt_style(self):
        symbol = self.test_market['symbol']
        self.exchange.order_book = {
            symbol: {
                'bids': [],
                'asks': [],
                **BOOK_METADATA
            }
        }
        reply = [17082, [7254.7, 2, 2.3]]

        channel, update = self.exchange.parse_order_book_ws(reply, self.test_market)
        update[symbol].update(BOOK_METADATA)

        correct_update = {
            'bids': [[7254.7, 2.3]],
            'asks': [],
            **BOOK_METADATA
        }
        self.assertEqual(correct_update, update[symbol])
