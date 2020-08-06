import ccxt.async_support as ccxt
import cryptoapi.base.exchange as exchange

from aiolimiter import AsyncLimiter
from ccxt.base.errors import BaseError


class Kraken(exchange.Exchange, ccxt.kraken):

    def __init__(self, config={}):
        ccxt.kraken.__init__(self, config=config)
        exchange.Exchange.__init__(self)
        self.channels[self.TICKER]['ex_name'] = 'ticker'
        self.channels[self.TRADES]['ex_name'] = 'trade'
        self.channels[self.ORDER_BOOK]['ex_name'] = 'book'
        self.channels[self.OHLCVS]['ex_name'] = 'ohlc'
        self.channels[self.TICKER]['has'] = True
        self.channels[self.TRADES]['has'] = True
        self.channels[self.ORDER_BOOK]['has'] = True
        self.channels[self.OHLCVS]['has'] = True
        self.channels_by_ex_name = self.create_channels_by_ex_name()
        # Maximum number of channels per connection.
        # Unlimited if equal to 10 ** 5.
        self.max_channels = 45
        # Number of connections that can be created per unit time,
        #   where the unit of time is in milliseconds.
        # Example: AsyncLimiter(1, 60000 / 1000) --> one connection per minute
        # Unlimited if equal to (10 ** 5, 60000).
        self.max_connections = {
            'public': AsyncLimiter(10 ** 5, 60000 / 1000),
            'private': AsyncLimiter(1, 60000 / 1000)
        }
        self.ws_endpoint = {
            'public': 'wss://ws.kraken.com',
            'private': ''
        }
        self.event = 'event'
        self.errors = ['error']
        self.subscribed = 'subscribed'
        # All message events that are not unified.
        self.others = ['subscriptionStatus', 'systemStatus', 'heartbeat']

    @property
    def markets_by_wsnames(self):
        return {
            market['info']['wsname']: market
            for market in self.markets.values()
            if self.key_exists(market['info'], 'wsname')
        } if self.markets else {}

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['info']['wsname'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'event': 'subscribe',
             'pair': [id],
             'subscription': {'name': ex_name, **params}}
            for id in ids
        ]

    async def subscribe_order_book(self, symbols, depth=100):
        params = {'depth': 100}
        requests = self.build_requests(symbols, self.ORDER_BOOK, params)
        await self.subscribe(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, timeframe='1m'):
        ex_timeframe = self.timeframes[timeframe]
        params = {'interval': ex_timeframe}
        requests = self.build_requests(symbols, self.OHLCVS, params)
        await self.subscribe(requests, public=True)

    def ex_channel_id_from_reply(self, reply):
        return reply[0]

    def register_channel(self, reply, websocket):
        ex_channel_id = reply['channelID']
        ex_name = reply['subscription']['name']
        name = self.channels_by_ex_name[ex_name]['name']
        wsname = reply['pair']
        symbol = self.markets_by_wsnames[wsname]['symbol']
        request = {
            'event': 'subscribe',
            'pair': wsname,
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
        if name == self.OHLCVS:
            ex_timeframe = request['subscription']['interval']
            ex_timeframes = {v: k for k, v in self.timeframes.items()}
            timeframe = ex_timeframes[ex_timeframe]
            channel.update({
                'timeframe': timeframe
            })
        self.connections[websocket].append(channel)  # Register channel

    def is_general_reply(self, reply):
        return isinstance(reply, dict)

    def parse_general_reply(self, reply, websocket):
        if reply[self.event] == 'subscriptionStatus':
            if reply['status'] == self.subscribed:
                return self.register_channel(reply, websocket)
        elif reply[self.event] in self.errors:
            return self.parse_error_ws(reply)
        else:
            return

    def parse_error_ws(self, reply, market=None):
        error_msg = reply['errorMessage']
        iso_format_msg = 'Currency pair not in ISO 4217-A3 format'
        if iso_format_msg in error_msg:
            return
        else:
            raise BaseError(reply['errorMessage'])

    def parse_ticker_ws(self, reply, market):
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
        return self.TICKER, {
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

    def parse_trades_ws(self, reply, market):
        trades = reply[1]
        return 'trades', self.parse_trades(trades, market)

    def parse_bid_ask(self, bid_ask, price_key=0, amount_key=1):
        price = float(bid_ask[0])
        amount = float(bid_ask[1])
        timestamp = float(bid_ask[2])
        return [price, amount, timestamp]

    def parse_order_book_ws(self, reply, market):
        order_book = reply[1]
        symbol = market['symbol']
        # Update
        if self.key_exists(order_book, 'b') or self.key_exists(order_book, 'a'):
            order_book = self.normalize_order_book_reply(order_book, bids_key='b', asks_key='a')
            update = super().parse_order_book(order_book, bids_key='b', asks_key='a')
            self.update_order_book(update, market)
        # Snapshot
        else:
            order_book = self.normalize_order_book_reply(order_book, bids_key='bs', asks_key='as')
            update = super().parse_order_book(order_book, bids_key='bs', asks_key='as')
            self.update_order_book(update, market, snapshot=True)
        return 'order_book', {symbol: update}

    def parse_ohlcvs_ws(self, reply, market):
        ohlcvs = reply[1]
        symbol = market['symbol']
        if not isinstance(ohlcvs[0], list):
            ohlcvs = [ohlcvs]
        return self.OHLCVS, {symbol: [[i[1], float(i[2]), float(i[3]), float(i[4]), float(i[5]), float(i[6])]
                             for i in ohlcvs]}
