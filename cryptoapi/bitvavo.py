import asyncio
import ccxt.async_support as ccxt
import exchange
from websockets_api.errors import UnknownResponse


class Bitvavo(exchange.Exchange, ccxt.bitvavo):

    def __init__(self, params={}):
        super(ccxt.coinbasepro, self).__init__(params)
        self.channels = {
            super().TICKER: {
                'ex_name': 'ticker24h',
                'has': True
            },
            super().TRADES: {
                'ex_name': 'trades',
                'has': True
            },
            super().ORDER_BOOK: {
                'ex_name': 'book',
                'has': True
            },
            super().OHLCVS: {
                'ex_name': 'candles',
                'has': True
            }
        }
        self.channels_by_ex_name = {
            v['ex_name']: {
                'name': symbol,
                'has': v['has']
            }
            for symbol, v in self.channels.items()
        }
        self.max_channels = 1000000  # Maximum number of channels per connection. No limit for coinbasepro
        self.max_connections = {'public': (1, 1000000), 'private': (0, 0)}
        self.connections = {}
        self.pending_channels = {}
        self.result = asyncio.Queue(maxsize=1)
        self.ws_endpoint = {
            'public': 'wss://ws.bitvavo.com/v2/',
            'private': ''
        }
        self.event = 'event'
        self.events = {
            self.parse_subscribed: ['subscriptions'],
            self.parse_unsubscribed: ['unsubscribe'],
            self.parse_error: [],
            self.parse_other: [],
            self.parse_ticker: ['ticker24h'],
            self.parse_trades: ['trades'],
            self.parse_order_book: ['book'],
            self.parse_ohlcvs: ['candle']
        }
        self.order_book = {}

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'action': 'subscribe',
             'channels': [{'name': ex_name, 'markets': [id]}.update(params)]}
            for id in ids
        ]

    # TODO
    async def build_unsubscribe_request(self, channel):
        pass

    async def subscribe_ticker(self, symbols, params={}):
        requests = self.build_requests(symbols, super().TICKER)
        await self.subscription_handler(requests, public=True)

    async def subscribe_trades(self, symbols, params={}):
        requests = self.build_requests(symbols, super().TRADES)
        await self.subscription_handler(requests, public=True)

    async def subscribe_order_book(self, symbols, params={}):
        requests = self.build_requests(symbols, super().ORDER_BOOK)
        await self.subscription_handler(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, params={}):
        requests = self.build_requests(symbols, super().OHLCVS)
        await self.subscription_handler(requests, public=True)

    def parse_subscribed(self, reply, websocket):
        ex_name = list(reply.keys())[0]
        name = self.channels_by_ex_name[ex_name]['name']
        if name == super().OHLCVS:
            ex_timeframe = reply[ex_name]
            timeframe = self.timeframes[ex_timeframe]
            params = {'interval': ex_timeframe}
            id = reply[ex_name][timeframe][0]
        else:
            id = reply[ex_name][0]
        symbol = self.markets[id]['symbol']
        request = self.build_request([symbol], name, params)
        channel = {
            'request': request,
            'channel_id': self.claim_channel_id(),
            'name': name,
            'symbol': symbol,
            'ex_channel_id': (ex_name, id)
        }
        self.connection_metadata_handler(websocket, channel)

    # TODO
    def parse_unsubscribed(self, reply):
        pass

    def parse_error(self, reply):
        pass  # Errors not defined in API documentation.

    def parse_ticker(self, ticker, market):
        return super().TICKER, super().parse_ticker(ticker, market)

    def parse_trades(self, trade, market):
        return super().TRADES, [super().parse_trade(trade, market)]

    def parse_order_book(self, order_book, market):
        return super().ORDER_BOOK, super().parse_order_book(order_book, market)

    def parse_ohlcvs(self, ohlcvs, market):
        return super().OHLCVS, super().parse_ohlcvs(ohlcvs, market)
