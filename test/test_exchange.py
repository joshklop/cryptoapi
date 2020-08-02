import unittest

from cryptoapi.base.exchange import Exchange
from test.helpers import AsyncContextManager, BOOK_METADATA, TEST_MARKET


class TestExchange(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.exchange = Exchange()
        self.test_market = TEST_MARKET

    def test_build_requests(self):
        symbol = self.test_market['symbol']
        self.assertEqual(self.exchange.build_requests(symbol, self.exchange.TICKER), [])

    def test_snapshot_updates_order_book(self):
        snapshot = {
            'bids': [[1, 1]],
            'asks': [[1, 1]],
            **BOOK_METADATA
        }

        self.exchange.update_order_book(snapshot, self.test_market, snapshot=True)

        symbol = self.test_market['symbol']
        self.assertEqual(snapshot, self.exchange.order_book[symbol])

    def test_remove_bidask_from_order_book(self):
        symbol = self.test_market['symbol']
        self.exchange.order_book = {
            symbol: {
                'bids': [[1, 1]],
                'asks': [[2, 1]],
                **BOOK_METADATA
            }
        }
        order_book_update = {
            'bids': [[1, 0]],
            'asks': [[2, 0]],
            **BOOK_METADATA
        }

        self.exchange.update_order_book(order_book_update, self.test_market)

        correct_book = {
            'bids': [],
            'asks': [],
            **BOOK_METADATA
        }
        self.assertEqual(correct_book, self.exchange.order_book[symbol])

    def test_add_bidask_to_order_book(self):
        symbol = self.test_market['symbol']
        self.exchange.order_book = {
            symbol: {
                'bids': [[1, 1]],
                'asks': [[2, 1]],
                **BOOK_METADATA
            }
        }
        order_book_update = {
            'bids': [[1.3, 1]],
            'asks': [[1.7, 1]],
            **BOOK_METADATA
        }

        self.exchange.update_order_book(order_book_update, self.test_market)

        correct_book = {
            'bids': [[1.3, 1], [1, 1]],
            'asks': [[1.7, 1], [2, 1]],
            **BOOK_METADATA
        }
        self.assertEqual(correct_book, self.exchange.order_book[symbol])

    def test_modify_bidask_in_order_book(self):
        symbol = self.test_market['symbol']
        self.exchange.order_book = {
            symbol: {
                'bids': [[1, 1]],
                'asks': [[2, 1]],
                **BOOK_METADATA
            }
        }
        order_book_update = {
            'bids': [[1, 0.7]],
            'asks': [[2, 0.7]],
            **BOOK_METADATA
        }

        self.exchange.update_order_book(order_book_update, self.test_market)

        # In this simple case, the update is the correct book because every
        # bid and every ask in the exchange order_book book gets replaced.
        self.assertEqual(order_book_update, self.exchange.order_book[symbol])

    def test_normalize_order_book_reply_bids(self):
        reply = {
            'bids': []
        }

        normalized_reply = self.exchange.normalize_order_book_reply(reply)

        correct_reply = {
            'bids': [],
            'asks': [],
        }
        self.assertEqual(correct_reply, normalized_reply)

    def test_normalize_order_book_reply_asks(self):
        reply = {
            'asks': []
        }

        normalized_reply = self.exchange.normalize_order_book_reply(reply)

        correct_reply = {
            'bids': [],
            'asks': []
        }
        self.assertEqual(correct_reply, normalized_reply)

    def test_claim_first_channel_id(self):
        self.exchange.connections = {}

        self.assertEqual(0, self.exchange.claim_channel_id())

    def test_claim_nonfirst_channel_id(self):
        channel_id = 0
        self.exchange.connections = {
            AsyncContextManager(): [{'channel_id': channel_id}]
        }

        self.assertEqual(channel_id + 1, self.exchange.claim_channel_id())

    def test_get_channels_empty_connections(self):
        self.exchange.connections = {}

        self.assertEqual([], self.exchange.get_channels())

    def test_get_channels_nonempty_connections(self):
        channel = {'channel_id': 0}
        self.exchange.connections = {
            AsyncContextManager(): [channel]
        }

        self.assertEqual([channel], self.exchange.get_channels())
