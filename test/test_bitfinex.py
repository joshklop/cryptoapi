import unittest

from cryptoapi.bitfinex import Bitfinex
from cryptoapi.base.errors import UnknownResponse
from test.helpers import AsyncContextManager, BOOK_METADATA, TEST_MARKET


class TestBitfinex(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with Bitfinex():
            self.exchange = Bitfinex()
            self.exchange.markets = {TEST_MARKET['symbol']: TEST_MARKET}
            self.exchange.markets_by_id = {TEST_MARKET['id']: TEST_MARKET}
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
        reply = [
            0,
            [
                123,
                456
            ]
        ]

        self.assertEqual(0, self.exchange.ex_channel_id_from_reply(reply))

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
