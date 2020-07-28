import asyncio
import websockets
from aiolimiter import AsyncLimiter
from errors import UnknownResponse


class Exchange():

    TICKER = 'ticker'
    TRADES = 'trades'
    ORDER_BOOK = 'order_book'
    OHLCVS = 'ohlcvs'

    def __init__(self):
        self.channels = {
            self.TICKER: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_ticker
            },
            self.TRADES: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_trades
            },
            self.ORDER_BOOK: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_order_book
            },
            self.OHLCVS: {
                'ex_name': '',
                'has': False,
                'parse': self.parse_ohlcvs
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

    async def throttle(self, throttled_method):
        async def wrapper(requests, public):
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
        self.pending_channels[websocket] = requests[:self.max_channels]
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
            return self.parse_subscribed(reply, websocket)
        elif reply[self.event] in self.others:
            return self.parse_other(reply)
        ex_channel_id = self.ex_channel_id_from_reply(reply)
        for c in self.connections[websocket]:
            if c['ex_channel_id'] == ex_channel_id:
                name = c['name']
                parse = self.channels[name]['parse']
                return parse(reply)
        raise UnknownResponse(reply)

    def parse_other(self, reply, websocket, market=None):
        return {'other': reply}

    def connection_metadata_handler(self, websocket, channel):
        self.connections[websocket].append(channel)  # Register channel
        # Clean self.pending_channels
        for ch in self.pending_channels[websocket]:
            if ch == channel['request']:
                index = self.pending_channels[websocket].index(ch)
                del self.pending_channels[websocket][index]
                if not self.pending_channels[websocket]:
                    del self.pending_channels[websocket]
                break

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

    def get_pending_channels(self):
        return [c for ws, c in self.pending_connections.values()] if self.pending_connections else []
