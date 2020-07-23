import asyncio
import ccxt.async_support as ccxt
import exchange
from ccxt.base.errors import BaseError
from errors import UnknownResponse


class Kraken(exchange.Exchange, ccxt.kraken):

    def __init__(self, params={}):
        super(ccxt.kraken, self).__init__(params)
        self.channels = {
            super().TICKER: {
                'ex_name': 'ticker',
                'has': True
            },
            super().TRADES: {
                'ex_name': 'trade',
                'has': True
            },
            super().ORDER_BOOK: {
                'ex_name': 'book',
                'has': True
            },
            super().OHLCVS: {
                'ex_name': 'ohlc',
                'has': True
            }
        }
        self.channels_by_ex_name = {
            v['ex_name']: {
                'name': symbol,
                'has': v['has']
            }
            for symbol, v in self.connections.items()
        }
        self.max_channels = 45  # Maximum number of channels per connection. Kraken has a really complicated algorithm, but this is a safe bet.
        self.max_connections = {'public': (1000000, 60000), 'private': (0, 0)}
        self.connections = {}
        self.pending_channels = {}
        self.result = asyncio.Queue(maxsize=1)
        self.ws_endpoint = {'public': 'wss://ws.kraken.com',
                            'private': ''}
        self.event = 'status'
        self.events = {
            self.parse_subscribed: ['subscribe'],
            self.parse_unsubscribed: ['unsubscribe'],
            self.parse_error: ['error'],
            self.parse_other: [],
            self.parse_ticker: [],
            self.parse_trades: [],
            self.parse_order_book: [],
            self.parse_ohlcvs: []
        self.order_book = {}

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'event': 'subscribe',
             'pair': [id],
             'subscription': {'name': ex_name}.update(params)}
            for id in ids
        ]

    # TODO
    async def build_unsubscribe_request(self, channel):
        pass

    async def subscribe_ticker(self, symbols):
        requests = self.build_requests(symbols, super().TICKER)
        await self.subscription_handler(requests, public=True)

    async def subscribe_trades(self, symbols):
        requests = self.build_requests(symbols, super().TRADES)
        await self.subscription_handler(requests, public=True)

    async def subscribe_order_book(self, symbols, depth=100):
        params = {'depth': 100}
        requests = self.build_requests(symbols, super().ORDER_BOOK, params)
        await self.subscription_handler(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, timeframe='1m'):
        ex_timeframe = self.timeframes[timeframe]
        params = {'interval': ex_timeframe}
        requests = self.build_requests(symbols, super().OHLCVS, params)
        await self.subscription_handler(requests, public=True)

    def parse_reply(self, reply, websocket):
        if isinstance(reply, dict):
            event = reply[self.event]
            for parse, events in self.events.items():
                if event in events:
                    return parse(reply, websocket)
        elif isinstance(reply, list):
            for c in self.connections[websocket]:
                if c['ex_channel_id'] == reply[0]:
                    name = c['name']
                    symbol = reply[-1]
                    market = self.markets_by_id[symbol]
                    if name == super().TICKER:
                        return self.parse_ticker(reply, websocket, market)
                    elif name == super().TRADES:
                        return self.parse_trades(reply, websocket, market)
                    elif name == super().ORDER_BOOK:
                        return self.parse_order_book(reply, websocket, market)
                    elif name == super().OHLCVS:
                        return self.parse_ohlcvs(reply, websocket, market)
                    else:
                        raise UnknownResponse(reply)
        else:
            raise UnknownResponse(reply)

    def parse_subscribed(self, reply, websocket, market=None):
        ex_channel_id = reply['channelID']
        ex_name = reply['subscription']['name']
        name = self.channels_by_ex_name[ex_name]['name']
        symbol = reply['pair']
        request = {
            'event': 'subscribe',
            'pair': symbol,
            'subscription': reply['subscription']
        }
        channel = {
            'request': request,
            'channel_id': self.claim_channel_id(),
            'ex_channel_id': ex_channel_id,
            'name': name,
            'ex_name': ex_name,
            'symbol': symbol
        }
        self.connection_metadata_handler(websocket, channel)

    # TODO
    def parse_unsubscribed(self, reply, websocket, market=None):
        pass

    def parse_error(self, reply, websocket, market=None):
        error_msg = reply['errorMessage']
        iso_format_msg = 'Currency pair not in ISO 4217-A3 format'
        if iso_format_msg in error_msg:
            return
        else:
            raise BaseError(reply['errorMessage'])

    def parse_ticker(self, reply, websocket, market=None):
        ticker = reply[1]
        symbol = market['symbol'] if market else None
        open = float(ticker['o'][0])
        close = float(ticker['c'][0])
        last = float(close)
        change = float(last - open)
        baseVolume = float(ticker['v'][1])
        vwap = float(ticker['p'][1])
        quoteVolume = None
        timestamp = self.milliseconds()
        if baseVolume is not None and vwap is not None:
            quoteVolume = baseVolume * vwap
        return super().TICKER, {
            'info': ticker,
            'symbol': symbol,
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'high': float(ticker['h'][0]),
            'low': float(ticker['l'][0]),
            'bid': float(ticker['b'][0]),
            'bidVolume': float(ticker['b'][2]),
            'ask': float(ticker['a'][0]),
            'askVolume': float(ticker['a'][2]),
            'vwap': vwap,
            'open': open,
            'close': close,
            'last': last,
            'previousClose': None,
            'change': change,
            'percentage': (change / open) * 100,
            'average': (last + open) / 2,
            'baseVolume': baseVolume,
            'quoteVolume': quoteVolume
        }

    def parse_trades(self, reply, websocket, market=None):
        trades = reply[1]
        timestamp = self.milliseconds()
        datetime = self.iso8601(timestamp)
        symbol = market['symbol']
        result = []
        for trade in trades:
            price = float(trade[0])
            amount = float(trade[1])
            order_type = trade[4]
            result.append({
                'info': trade,
                'id': None,
                'timestamp': timestamp,
                'datetime': datetime,
                'symbol': symbol,
                'order': None,
                'type': order_type,
                'side': trade[3],
                'takerOrMaker': 'maker' if order_type == 'limit' else 'taker',
                'price': price,
                'amount': amount,
                'cost': price * amount,
                'fee': None
            })
        return super().TRADES, result

    # Override ccxt.Exchange.safe_integer. Kraken's websocket stream sends timestamps as floats.
    # This is particularly important for parse_order_book_.
    # FIXME: this is dangerous. Affects other methods as well, not just parse_order_book.
    def safe_integer(self, dictionary, key):
        return float(dictionary[key])

    def parse_order_book(self, reply, websocket, market=None):
        order_book = reply[1]
        symbol = market['symbol']
        # Snapshot
        if super().key_exists(order_book, 'bs'):
            order_book = super().parse_order_book(order_book, bids_key='bs', asks_key='as')
            bids, asks = [ask[:2] for ask in order_book['asks']], [ask[:2] for ask in order_book['asks']]
            self.order_book[symbol] = {'bids': bids, 'asks': asks}
        # Updates
        else:
            order_book = super().parse_order_book(order_book, bids_key='b', asks_key='a')
            bids, asks = [ask[:2] for ask in order_book['asks']], [ask[:2] for ask in order_book['asks']]
            self.order_book[symbol]['bids'].extend(bids)
            self.order_book[symbol]['asks'].extend(asks)
        timestamp = self.milliseconds()
        self.order_book[symbol].update({
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'nonce': None
        })
        self.order_book[symbol]['bids'] = sorted(self.order_book[symbol]['bids'], key=lambda l: l[0], reverse=True)
        self.order_book[symbol]['asks'] = sorted(self.order_book[symbol]['asks'], key=lambda l: l[0])
        return super().ORDER_BOOK, {symbol: self.order_book[symbol]}

    def parse_ohlcvs(self, reply, websocket, market=None):
        ohlcvs = reply[1]
        symbol = market['symbol']
        if not isinstance(ohlcvs[0], list):
            ohlcvs = [ohlcvs]
        return super().OHLCVS, {symbol: [[i[1], float(i[2]), float(i[3]), float(i[4]), float(i[5]), float(i[6])]
                                for i in ohlcvs]}
