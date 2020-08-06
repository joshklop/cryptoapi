import unittest

from cryptoapi.bitvavo import Bitvavo
from test.helpers import AsyncContextManager, BOOK_METADATA, TEST_MARKET


class TestBitvavo(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with Bitvavo():
            self.exchange = Bitvavo()
            self.exchange.markets = {TEST_MARKET['symbol']: TEST_MARKET}
            self.exchange.markets_by_id = {TEST_MARKET['id']: TEST_MARKET}
            self.test_market = TEST_MARKET

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
        self.exchange.order_book = {
            self.test_market['symbol']: {
                'bids': [],
                'asks': [],
                **BOOK_METADATA
            }
        }
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
