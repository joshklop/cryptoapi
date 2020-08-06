__all__ = [
    'Exchange'
]


import asyncio
import ccxt
import websockets

from aiolimiter import AsyncLimiter
from cryptoapi.base.errors import UnknownResponse


class Exchange(ccxt.Exchange):

    TICKER = 'ticker'
    TRADES = 'trades'
    ORDER_BOOK = 'order_book'
    OHLCVS = 'ohlcvs'

    def __init__(self):
        self.channels = {
            self.TICKER: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_ticker_ws
            },
            self.TRADES: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_trades_ws
            },
            self.ORDER_BOOK: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_order_book_ws
            },
            self.OHLCVS: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_ohlcvs_ws
            }
        }
        self.channels_by_ex_name = self.create_channels_by_ex_name()
        self.max_channels = 0  # Maximum number of channels per connection.
        # Number of connections that can be created per unit time,
        #   where the unit of time is in milliseconds.
        # Example: AsyncLimiter(1, 60000 / 1000) --> one connection per minute
        self.max_connections = {
            'public': AsyncLimiter(1, 60000 / 1000),
            'private': AsyncLimiter(1, 60000 / 1000)
        }
        self.connections = {}
        self.result = asyncio.Queue(maxsize=1)
        self.ws_endpoint = {
            'public': '',
            'private': ''
        }
        self.event = ''
        self.subscribed = ''
        self.errors = {}
        self.order_book = {}
        # All message events that are not unified.
        self.others = []

    async def subscribe_ticker(self, symbols, params={}):
        requests = self.build_requests(symbols, self.TICKER)
        await self.subscribe(requests, public=True)

    async def subscribe_trades(self, symbols, params={}):
        requests = self.build_requests(symbols, self.TRADES)
        await self.subscribe(requests, public=True)

    async def subscribe_order_book(self, symbols, params={}):
        requests = self.build_requests(symbols, self.ORDER_BOOK)
        await self.subscribe(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, params={}):
        requests = self.build_requests(symbols, self.OHLCVS)
        await self.subscribe(requests, public=True)

    def build_requests(self, symbols, channel):
        return []

    async def subscribe(self, requests, public):
        rate_limit = self.max_connections['public'] if public else self.max_connections['private']
        endpoint = self.ws_endpoint['public'] if public else self.ws_endpoint['private']
        while requests:
            async with rate_limit:
                websocket = await websockets.connect(endpoint)
                self.connections[websocket] = []  # Register websocket
                await self.send(websocket, requests[:self.max_channels])
                del requests[:self.max_channels]
                await asyncio.create_task(self.consumer(websocket))

    async def send(self, websocket, requests):
        requests = [super(Exchange, self).json(r) for r in requests]
        tasks = [
            asyncio.create_task(websocket.send(r))
            for r in requests
        ]
        for t in tasks:
            await t

    async def consumer(self, websocket):
        async for reply in websocket:
            reply = super().unjson(reply)
            if self.is_general_reply(reply):
                parsed_reply = self.parse_general_reply(reply, websocket)
            else:
                parsed_reply = self.parse_market_reply(reply, websocket)
            if parsed_reply:
                await self.result.put(parsed_reply)

    def is_general_reply(self, reply):
        return reply[self.event] == self.subscribed or reply[self.event] in self.errors

    def parse_general_reply(self, reply, websocket):
        if isinstance(reply, dict):
            if reply[self.event] == self.subscribed:
                return self.register_channel(reply, websocket)
            elif reply[self.event] in self.errors:
                return self.parse_error_ws(reply)

    def parse_market_reply(self, reply, websocket):
        ex_channel_id = self.ex_channel_id_from_reply(reply)
        for c in self.connections[websocket]:
            if c['ex_channel_id'] == ex_channel_id:
                name = c['name']
                symbol = c['symbol']
                market = self.markets[symbol]
                parse = self.channels[name]['parse']
                return parse(reply, market)
        raise UnknownResponse(reply)

    def register_channel(self, reply, websocket):
        self.connections[websocket] = reply

    def find_not_subbed_symbol(self, subed_ids):
        subed_symbols = [
            channel['symbol']
            for channel in self.get_channels()
        ]  # Subscribed and registered symbols
        id, symbol = [
            (id, self.markets_by_id[id]['symbol'])
            for id in subed_ids
            if self.markets_by_id[id]['symbol'] not in subed_symbols
        ].pop()  # Find the only subed id that isn't registered yet
        return id, symbol


    def parse_error_ws(self, reply, market=None):
        raise self.errors[reply['code']]

    def parse_ticker_ws(self, reply, market):
        pass

    def parse_trades_ws(self, reply, market):
        pass

    def parse_order_book_ws(self, reply, market):
        pass

    def parse_ohlcvs_ws(self, reply, market):
        pass

    def parse_other_ws(self, reply):
        return 'other', reply

    def update_order_book(self, update, market, snapshot=False):
        symbol = market['symbol']
        if snapshot:
            self.order_book[symbol] = update
            return
        cupdate = update.copy()
        self.order_book[symbol]['timestamp'] = cupdate.pop('timestamp')
        self.order_book[symbol]['datetime'] = cupdate.pop('datetime')
        self.order_book[symbol]['nonce'] = cupdate.pop('nonce')
        prices = {
            'bids': [bid[0] for bid in self.order_book[symbol]['bids']],
            'asks': [ask[0] for ask in self.order_book[symbol]['asks']]
        }
        for key, bids_asks in cupdate.items():
            for bid_ask in bids_asks:
                price = bid_ask[0]
                amount = bid_ask[1]
                if price in prices[key]:
                    # The index for the bid_ask in question
                    idx = prices[key].index(price)
                    if amount == 0:
                        del self.order_book[symbol][key][idx]
                        # Make sure prices's indices are synced
                        # with self.order_book
                        del prices[key][idx]
                    else:
                        self.order_book[symbol][key][idx] = bid_ask
                else:
                    self.order_book[symbol][key].append(bid_ask)
        self.order_book[symbol]['bids'] = self.sort_by(self.order_book[symbol]['bids'], 0, True)
        self.order_book[symbol]['asks'] = self.sort_by(self.order_book[symbol]['asks'], 0)

    def normalize_order_book_reply(self, order_book, bids_key='bids', asks_key='asks'):
        if not self.key_exists(order_book, bids_key):
            order_book[bids_key] = []
        elif not self.key_exists(order_book, asks_key):
            order_book[asks_key] = []
        return order_book

    def claim_channel_id(self):
        channels = self.get_channels()
        if channels:
            channel_ids = [c['channel_id'] for c in channels]
            return max(channel_ids) + 1
        else:
            return 0

    def create_channels_by_ex_name(self):
        return {
            v['ex_name']: {
                'name': name,
                'has': v['has'],
                'parse': v['parse']
            }
            for name, v in self.channels.items()
        }

    def get_channels(self):
        return [c for chans in self.connections.values() for c in chans] if self.connections else []
