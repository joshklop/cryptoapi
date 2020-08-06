import ccxt.async_support as ccxt
import cryptoapi.base.exchange as exchange

from aiolimiter import AsyncLimiter
from ccxt.base.errors import BaseError
from ccxt.base.errors import ExchangeError
from ccxt.base.errors import OnMaintenance
from cryptoapi.base.errors import SubscribeError
from cryptoapi.base.errors import UnsubscribeError
from cryptoapi.base.errors import ChannelLimitExceeded
from cryptoapi.base.errors import Reconnect
from cryptoapi.base.errors import UnknownResponse


class Bitfinex(exchange.Exchange, ccxt.bitfinex2):

    def __init__(self, config={}):
        ccxt.bitfinex2.__init__(self, config=config)
        exchange.Exchange.__init__(self)
        self.channels[self.TICKER]['ex_name'] = 'ticker'
        self.channels[self.TRADES]['ex_name'] = 'trades'
        self.channels[self.ORDER_BOOK]['ex_name'] = 'book'
        self.channels[self.OHLCVS]['ex_name'] = 'candles'
        self.channels[self.TICKER]['has'] = True
        self.channels[self.TRADES]['has'] = True
        self.channels[self.ORDER_BOOK]['has'] = True
        self.channels[self.OHLCVS]['has'] = True
        self.channels_by_ex_name = self.create_channels_by_ex_name()
        # Maximum number of channels per connection.
        # Unlimited if equal to 10 ** 5.
        self.max_channels = 25
        # Number of connections that can be created per unit time,
        # where the unit of time is in milliseconds.
        # Example: AsyncLimiter(1, 60000 / 1000) --> one connection per minute
        # Unlimited if equal to (10 ** 5, 60000).
        self.max_connections = {
            'public': AsyncLimiter(20, 60000 / 1000),
            'private': AsyncLimiter(1, 60000 / 1000)
        }
        self.ws_endpoint = {
            'public': 'wss://api-pub.bitfinex.com/ws/2',
            'private': 'wss://api.bitfinex.com/ws/2'
        }
        self.event = 'event'
        self.subscribed = 'subscribed'
        self.errors = {
            10000: BaseError('Unknown event.'),
            10001: ExchangeError('Unknown pair.'),
            10300: SubscribeError,
            10301: SubscribeError('Already subscribed.'),
            10302: SubscribeError('Unknown channel.'),
            10305: ChannelLimitExceeded,
            10400: UnsubscribeError,
            10401: UnsubscribeError('Not subscribed.'),
        }
        # All message events that are not unified.
        self.others = ['info']

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'event': 'subscribe',
             'channel': ex_name,
             'symbol': id,
             **params}
            for id in ids
        ]

    async def subscribe_order_book(self, symbols):
        params = {
            'prec': 'P0',
            'freq': 'F0',
            'len': 100
        }
        requests = self.build_requests(symbols, self.ORDER_BOOK, params)
        await self.subscribe(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, timeframe='1m'):
        ex_timeframe = self.timeframes[timeframe]
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[self.OHLCVS]['ex_name']
        requests = [
            {'event': 'subscribe',
             'channel': ex_name,
             'key': 'trade:' + ex_timeframe + ':' + id}
            for id in ids
        ]
        await self.subscribe(requests, public=True)

    def ex_channel_id_from_reply(self, reply):
        return reply[0]

    def register_channel(self, reply, websocket):
        channel = {}
        ex_channel_id = reply['chanId']
        channel_id = self.claim_channel_id()
        ex_name = reply['channel']
        name = self.channels_by_ex_name[ex_name]['name']
        channel.update({
            'request': {'event': 'subscribe', 'channel': ex_name},
            'channel_id': channel_id,
            'ex_channel_id': ex_channel_id,
            'name': name
        })
        if name == self.OHLCVS:
            key = reply['key']
            ex_timeframe, id = key.split(sep=':')[1:3]
            ex_timeframes = {v: k for k, v in self.timeframes.items()}
            timeframe = ex_timeframes[ex_timeframe]
            symbol = self.markets_by_id[id]['symbol']
            channel['request'].update({'key': key})
            channel.update({
                'symbol': symbol,
                'timeframe': timeframe
            })
        else:
            id = reply['symbol']
            symbol = self.markets_by_id[id]['symbol']
            channel['request'].update({'symbol': id})
            channel.update({'symbol': symbol})
            if name == self.ORDER_BOOK:
                depth = int(reply['len'])
                channel['request'].update({
                    'prec': reply['prec'],
                    'freq': reply['freq'],
                    'len': depth
                })
        self.connections[websocket].append(channel)  # Register channel.

    def is_general_reply(self, reply):
        if isinstance(reply, list):
            return reply[1] == 'hb'
        return reply[self.event] in [self.subscribed, 'info']

    def parse_other_ws(self, reply):
        code = reply['code'] if self.key_exists(reply, 'code') else None
        if code == 20051:
            raise Reconnect('Unsubscribe/subscribe to all channels.')
        elif code == 20060:
            # TODO handle this issue once unsubscribe feature is added.
            raise OnMaintenance(
                'Exchange is undergoing maintenance.'
                + ' Pause activity for 2 minutes and then'
                + ' unsubscribe/subscribe all channels.'
            )
        if self.key_exists(reply, 'version'):
            if reply['version'] == 2:
                pass
            else:
                raise ExchangeError('API version number changed.')

    def parse_ticker_ws(self, reply, market):
        ticker = reply[1]
        return self.TICKER, self.parse_ticker(ticker, market)

    def parse_trades_ws(self, reply, market):
        trades = reply[1] if len(reply) < 3 else reply[2]
        if not isinstance(trades[0], list):
            trades = [trades]
        return self.TRADES, self.parse_trades(trades, market)

    def parse_order_book_ws(self, reply, market):
        order_book = reply[1]
        symbol = market['symbol']
        timestamp = self.milliseconds()
        update = {
            'bids': [],
            'asks': [],
            'timestamp': timestamp,
            'datetime': self.iso8601(timestamp),
            'nonce': None,
        }
        if not isinstance(order_book[0], list):
            order_book = [order_book]
            snapshot = False
        else:
            snapshot = True
        for i in range(0, len(order_book)):
            order = order_book[i]
            price = order[0]
            side = 'bids' if (order[2] > 0) else 'asks'
            amount = abs(order[2])
            update[side].append([price, amount])
        self.update_order_book(update, market, snapshot=snapshot)
        return self.ORDER_BOOK, {symbol: update}

    def parse_ohlcvs_ws(self, reply, market):
        ohlcvs = reply[1]
        symbol = market['symbol']
        if not isinstance(ohlcvs[0], list):
            ohlcvs = [ohlcvs]
        ohlcvs = [[i[0], i[1], i[3], i[4], i[2], i[5]] for i in ohlcvs]
        return self.OHLCVS, {symbol: self.sort_by(ohlcvs, 0)}
