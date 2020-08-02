import unittest
from cryptoapi.kraken import Kraken
from test.helpers import AsyncContextManager, BOOK_METADATA

TEST_MARKET = {
    'percentage': True,
    'tierBased': True,
    'taker': 0.0026,
    'maker': 0.0016,
    'tiers': {
        'taker': [
            [0, 0.0026],
            [50000, 0.0024],
            [100000, 0.0022],
            [250000, 0.002],
            [500000, 0.0018],
            [1000000, 0.0016],
            [2500000, 0.0014],
            [5000000, 0.0012],
            [10000000, 0.0001]
        ],
        'maker': [
            [0, 0.0016],
            [50000, 0.0014],
            [100000, 0.0012],
            [250000, 0.001],
            [500000, 0.0008],
            [1000000, 0.0006],
            [2500000, 0.0004],
            [5000000, 0.0002],
            [10000000, 0.0]
        ]
    },
    'precision': {
        'amount': 8,
        'price': 1
    },
    'limits': {
        'amount': {
            'min': 0.002,
            'max': 100000000.0
        },
        'price': {
            'min': 0.1,
            'max': None
        },
        'cost': {
            'min': 0,
            'max': None
        }
    },
    'id': 'XXBTZUSD',
    'symbol': 'BTC/USD',
    'base': 'BTC',
    'quote': 'USD',
    'baseId': 'XXBT',
    'quoteId': 'ZUSD',
    'darkpool': False,
    'info': {
        'altname': 'XBTUSD',
        'wsname': 'XBT/USD',
        'aclass_base': 'currency',
        'base': 'XXBT',
        'aclass_quote': 'currency',
        'quote': 'ZUSD',
        'lot': 'unit',
        'pair_decimals': 1,
        'lot_decimals': 8,
        'lot_multiplier': 1,
        'leverage_buy': [2, 3, 4, 5],
        'leverage_sell': [2, 3, 4, 5],
        'fees': [
            [0, 0.26],
            [50000, 0.24],
            [100000, 0.22],
            [250000, 0.2],
            [500000, 0.18],
            [1000000, 0.16],
            [2500000, 0.14],
            [5000000, 0.12],
            [10000000, 0.1]
        ],
        'fees_maker': [
            [0, 0.16],
            [50000, 0.14],
            [100000, 0.12],
            [250000, 0.1],
            [500000, 0.08],
            [1000000, 0.06],
            [2500000, 0.04],
            [5000000, 0.02],
            [10000000, 0]
        ],
        'fee_volume_currency': 'ZUSD',
        'margin_call': 80,
        'margin_stop': 40,
        'ordermin': '0.002'
    },
    'altname': 'XBTUSD',
    'active': True
}


class TestKraken(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with Kraken():
            self.exchange = Kraken()
            symbol = TEST_MARKET['symbol']
            self.exchange.markets = {symbol: TEST_MARKET}
            self.exchange.markets_by_id = {TEST_MARKET['id']: TEST_MARKET}
            self.test_market = self.exchange.markets[symbol]

    def test_build_requests(self):
        symbol = [self.test_market['symbol']]
        name = self.exchange.TICKER

        requests = self.exchange.build_requests(symbol, name)

        correct_requests = [{
            'event': 'subscribe',
            'pair': [self.test_market['id']],
            'subscription': {'name': self.exchange.channels[name]['ex_name']}
        }]
        self.assertEqual(correct_requests, requests)

    def test_ex_channel_id_from_reply(self):
        correct_ex_channel_id = 42
        reply = [
            correct_ex_channel_id,
                [
                    "1542057314.748456",
                    "1542057360.435743",
                    "3586.70000",
                    "3586.70000",
                    "3586.60000",
                    "3586.60000",
                    "3586.68894",
                    "0.03373000",
                    2
                ],
            "ohlc-5",
            "XBT/USD"
        ]

        self.assertEqual(correct_ex_channel_id, self.exchange.ex_channel_id_from_reply(reply))

    def test_register_channel(self):
        """Ticker, trades, order_book"""
        name = self.exchange.TICKER
        ex_name = self.exchange.channels[name]['ex_name']
        id = self.test_market['id']
        ex_channel_id = 0
        reply = {
            "channelID": ex_channel_id,
            "channelName": ex_name,
            "event": "subscriptionStatus",
            "pair": id,
            "status": "subscribed",
            "subscription": {
                "name": ex_name
            }
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_registration = [{
            'request': {
                'event': 'subscribe',
                'pair': self.test_market['id'],
                'subscription': reply['subscription']
            },
            'channel_id': 0,
            'ex_channel_id': ex_channel_id,
            'name': name,
            'ex_name': ex_name,
            'symbol': self.test_market['symbol']
        }]
        self.assertEqual(correct_registration, self.exchange.connections[websocket_mock])

    def test_register_ohlcvs_channel(self):
        """OHLCVS only"""
        name = self.exchange.OHLCVS
        ex_name = self.exchange.channels[name]['ex_name']
        ex_channel_id = 0
        id = self.test_market['id']
        ex_timeframe = 5
        timeframe = '5m'
        reply = {
            "channelID": ex_channel_id,
            "channelName": ex_name,
            "event": "subscriptionStatus",
            "pair": id,
            "status": "subscribed",
            "subscription": {
                "name": ex_name,
                "interval": ex_timeframe
            }
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_registration = [{
            'request': {
                'event': 'subscribe',
                'pair': id,
                'subscription': reply['subscription']
            },
            'channel_id': 0,
            'ex_channel_id': ex_channel_id,
            'name': name,
            'ex_name': ex_name,
            'symbol': self.test_market['symbol'],
            'timeframe': timeframe
        }]
        self.assertEqual(correct_registration, self.exchange.connections[websocket_mock])

    def test_parse_order_book_snapshot_ccxt_style(self):
        reply = [
            0,
            {
                "as": [
                    [
                        "5541.30000",
                        "2.50700000",
                        "1534614248.123678"
                    ]
                ],
                "bs": [
                    [
                        "5541.20000",
                        "1.52900000",
                        "1534614248.765567"
                    ],
                ]
            },
            "book-100",
            "XBT/USD"
        ]

        channel, update = self.exchange.parse_order_book_ws(reply, self.test_market)
        symbol = self.test_market['symbol']
        update[symbol].update(BOOK_METADATA)

        correct_book = {
            'bids': [[5541.20000, 1.52900000, 1534614248.765567]],
            'asks': [[5541.30000, 2.50700000, 1534614248.123678]],
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
        reply = [
            1234,
            {
                "b": [
                    [
                        "5541.30000",
                        "1.00000000",
                        "1534614335.345903"
                    ]
                ],
                "c": "974942666"
            },
            "book-10",
            "XBT/USD"
        ]

        channel, update = self.exchange.parse_order_book_ws(reply, self.test_market)
        update[symbol].update(BOOK_METADATA)

        correct_book = {
            'bids': [[5541.30000, 1.00000000, 1534614335.345903]],
            'asks': [],
            **BOOK_METADATA
        }
        self.assertEqual(correct_book, update[symbol])
