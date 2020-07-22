import time
import asyncio
import websockets
import ccxt.async_support as ccxt


class Exchange(ccxt.Exchange):

    TICKER = 'ticker'
    TRADES = 'trades'
    ORDER_BOOK = 'order_book'
    OHLCVS = 'ohlcvs'

    async def send(self, websocket, requests):
        requests = [super(Exchange, self).json(r) for r in requests]
        tasks = [
            asyncio.create_task(websocket.send(r))
            for r in requests
        ]
        for t in tasks:
            await t

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
            await self.subscribe(websocket, requests[:self.max_channels], public)
            del requests[:self.max_channels]
            tasks.append(asyncio.create_task(self.consumer_handler(websocket, public)))
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

    # Warning: untested! Not recommended for use. Kind of pointless anyway.
    # Will not work.
    async def unsubscribe(self, channel_ids):
        # Filter connections
        connections = self.public_connections.copy()
        connections.update(self.private_connections.copy())
        unsubscribe = {ws: [chan
                            for chan in v
                            if chan['channel_id'] in channel_ids]
                       for ws, v in connections.items()}
        for ws, v in unsubscribe.items():
            requests = [self.build_unsubscribe_request(i) for i in v]
            await self.send(ws, requests)

    def connection_metadata_handler(self, websocket, channel):
        self.connections[websocket].append(channel)  # Register channel
        # Clean pending_channels
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

    @staticmethod
    def get_channels(connections):
        return [i for v in connections.values() for i in v] if connections else []
