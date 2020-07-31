import asyncio
import ccxt
import websockets
from aiolimiter import AsyncLimiter
from cryptoapi.errors import UnknownResponse


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
        self.channels_by_ex_name = self.channels_by_ex_name()
        self.max_channels = 0  # Maximum number of channels per connection.
        # Number of connections that can be created per unit time,
        #   where the unit of time is in milliseconds.
        # Example: AsyncLimiter(1, 60000 / 1000) --> one connection per minute
        self.max_connections = {
            'public': AsyncLimiter(0, 0 / 1000),
            'private': AsyncLimiter(0, 0 / 1000)
        }
        self.connections = {}
        self.pending_channels = {}
        self.result = asyncio.Queue(maxsize=1)
        self.ws_endpoint = {
            'public': '',
            'private': ''
        }
        self.event = ''
        self.subscribed = ''
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

    def throttle(throttled_method):
        async def wrapper(self, requests, public):
            rate_limit = self.max_connections['public'] if public else self.max_connections['private']
            while requests:
                async with rate_limit:
                    await self.throttled_method()
        return wrapper

    @throttle
    async def subscribe(self, requests, public):
        endpoint = self.ws_endpoint['public'] if public else self.ws_endpoint['private']
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
            parsed_reply = self.parse_reply(super().unjson(reply), websocket)
            await self.result.put(parsed_reply)

    def parse_reply(self, reply, websocket):
        if reply[self.event] == self.subscribed:
            return self.register_channel(reply, websocket)
        elif reply[self.event] in self.others:
            return self.parse_other(reply)
        ex_channel_id = self.ex_channel_id_from_reply(reply)
        for c in self.connections[websocket]:
            if c['ex_channel_id'] == ex_channel_id:
                name = c['name']
                symbol = c['symbol']
                market = self.markets[symbol]
                parse = self.channels[name]['parse']
                return parse(reply, market)
        raise UnknownResponse(reply)

    def parse_ticker_ws(self, reply, market):
        pass

    def parse_trades_ws(self, reply, market):
        pass

    def parse_order_book_ws(self, reply, market):
        pass

    def parse_ohlcvs_ws(self, reply, market):
        pass

    def parse_other(self, reply, market=None):
        return {'other': reply}

    def update_order_book(self, update, market, snapshot=False):
        symbol = market['symbol']
        if snapshot:
            self.order_book[symbol] = update
            return
        self.order_book[symbol]['timestamp'] = update.pop('timestamp')
        self.order_book[symbol]['datetime'] = update.pop('datetime')
        self.order_book[symbol]['nonce'] = update.pop('nonce')
        prices = {
            'bids': [bid[0] for bid in self.order_book[symbol]['bids']],
            'asks': [ask[0] for ask in self.order_book[symbol]['asks']]
        }
        for key, bids_asks in update.items():
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

    def channels_by_ex_name(self):
        return {
            v['ex_name']: {
                'name': name,
                'has': v['has'],
                'parse': v['parse']
            }
            for name, v in self.channels.items()
        }

    def get_channels(self):
        return [c for ws, c in self.connections.values()] if self.connections else []
