import time
import asyncio
import websockets
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
                'has': True,
                'parse': self.parse_ticker
            },
            self.TRADES: {
                'ex_name': '',
                'has': True,
                'parse': self.parse_trades
            },
            self.ORDER_BOOK: {
                'ex_name': '',
                'has': True,
                'parse': self.parse_order_book
            },
            self.OHLCVS: {
                'ex_name': '',
                'has': True,
                'parse': self.parse_ohlcvs
            }
        }
        self.channels_by_ex_name = self.channels_by_ex_name()
        self.max_channels = 0  # Maximum number of channels per connection.
        # Number of connections that can be created per unit time,
        #   where the unit of time is in milliseconds.
        # Example: (1, 60000) --> one connection per minute
        self.max_connections = {'public': (0, 0), 'private': (0, 0)}
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
        await self.subscription_handler(requests, public=True)

    async def subscribe_trades(self, symbols, params={}):
        requests = self.build_requests(symbols, self.TRADES)
        await self.subscription_handler(requests, public=True)

    async def subscribe_order_book(self, symbols, params={}):
        requests = self.build_requests(symbols, self.ORDER_BOOK)
        await self.subscription_handler(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, params={}):
        requests = self.build_requests(symbols, self.OHLCVS)
        await self.subscription_handler(requests, public=True)

    async def subscription_handler(self, requests, public):
        if public:
            max_conn = self.max_connections['public']
            endpoint = self.ws_endpoint['public']
        else:
            max_conn = self.max_connections['private']
            endpoint = self.ws_endpoint['private']
        tasks = []
        i = 0
        start = time.time()
        while requests:
            # Throttle connections.
            if i == max_conn[0]:
                wait = max_conn[1] - (time.time() - start)
                if wait > 0:
                    await asyncio.sleep(wait / 1000)
                i = 0
                start = time.time()
            websocket = await websockets.connect(endpoint)
            self.connections[websocket] = []  # Register websocket
            await self.subscribe(websocket, requests[:self.max_channels])
            del requests[:self.max_channels]
            tasks.append(asyncio.create_task(self.consumer_handler(websocket)))
            i += 1
        for t in tasks:
            await t

    async def subscribe(self, websocket, requests):
        self.pending_channels[websocket] = requests
        await self.send(websocket, requests)

    async def consumer_handler(self, websocket):
        async for reply in websocket:
            parsed_reply = self.parse_reply(super().unjson(reply), websocket)
            if parsed_reply:
                await self.result.put(parsed_reply)

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
        channels = Exchange.get_channels(self.connections)
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
