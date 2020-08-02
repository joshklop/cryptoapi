import unittest

from cryptoapi.coinbasepro import Coinbasepro
from test.helpers import AsyncContextManager, BOOK_METADATA, TEST_MARKET


class TestKraken(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        async with Coinbasepro():
            self.exchange = Coinbasepro()
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
                'type': 'subscribe',
                'channels': [{'name': ex_name, 'product_ids': [self.test_market['id']]}]}
        ]
        self.assertEqual(correct_requests, requests)

    def test_ex_channel_id_from_reply(self):
        reply = {
            'type': self.exchange.TICKER,
            'product_id': self.test_market['id']
        }

        self.assertEqual(
            (reply['type'], reply['product_id']),
            self.exchange.ex_channel_id_from_reply(reply)
        )

    def test_register_channel(self):
        # All channels go through the same process so no need to create
        # separate tests.
        name = self.exchange.TICKER
        channel = self.exchange.channels[name]
        ex_name = channel['ex_name']
        id = self.test_market['id']
        reply = {
            'type': 'subscriptions',
            'channels': [
                {
                    'name': ex_name,
                    'product_ids': [id]
                }
            ]
        }
        websocket_mock = AsyncContextManager()
        self.exchange.connections[websocket_mock] = []

        self.exchange.register_channel(reply, websocket_mock)

        correct_registration = {
            'request': {
                'type': 'subscribe',
                'channels': [{'name': ex_name, 'product_ids': [id]}],
            },
            'channel_id': 0,
            'ex_channel_id': (ex_name, id),
            'name': name,
            'symbol': self.test_market['symbol']
        }
        self.assertEqual([correct_registration], self.exchange.connections[websocket_mock])

    def test_parse_order_book_snapshot_ccxt_style(self):
        reply = {
            "type": "snapshot",
            "product_id": "BTC-USD",
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

    def test_parse_order_book_update_ccxt_style(self):
        self.exchange.order_book = {
            self.test_market['symbol']: {
                'bids': [],
                'asks': [],
                **BOOK_METADATA
            }
        }
        reply = {
            "type": "l2update",
            "product_id": "BTC-USD",
            "time": "2019-08-14T20:42:27.265Z",
            "changes": [
                [
                    "buy",
                    "10101.80000000",
                    "0.162567"
                ]
            ]
        }

        channel, update = self.exchange.parse_order_book_ws(reply, self.test_market)
        update.update(BOOK_METADATA)

        correct_update = {
            'bids': [[10101.80000000, 0.162567]],
            'asks': [],
            **BOOK_METADATA
        }
        symbol = self.test_market['symbol']
        self.assertEqual(correct_update, update[symbol])
