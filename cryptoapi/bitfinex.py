import asyncio
import ccxt.async_support as ccxt
import exchange
from aiolimiter import AsyncLimiter
from ccxt.base.errors import BaseError
from ccxt.base.errors import ExchangeError
from ccxt.base.errors import NetworkError
from ccxt.base.errors import OnMaintenance
from errors import SubscribeError
from errors import UnsubscribeError
from errors import ChannelLimitExceeded
from errors import Reconnect
from errors import UnknownResponse


class Bitfinex(exchange.Exchange, ccxt.bitfinex2):

    def __init__(self, params={}):
        super(ccxt.bitfinex2, self).__init__(params)
        super(exchange.Exchange, self).__init__()
        self.channels[self.TICKER]['ex_name'] = 'ticker'
        self.channels[self.TRADES]['ex_name'] = 'trades'
        self.channels[self.ORDER_BOOK]['ex_name'] = 'book'
        self.channels[self.OHLCVS]['ex_name'] = 'candles'
        self.channels[self.TICKER]['has'] = True
        self.channels[self.TRADES]['has'] = True
        self.channels[self.ORDER_BOOK]['has'] = True
        self.channels[self.OHLCVS]['has'] = True
        self.channels_by_ex_name = self.channels_by_ex_name()
        # Maximum number of channels per connection.
        # Unlimited if equal to 10 ** 5.
        self.max_channels = 25
        # Number of connections that can be created per unit time,
        #   where the unit of time is in milliseconds.
        # Example: AsyncLimiter(1, 60000 / 1000) --> one connection per minute
        # Unlimited if equal to (10 ** 5, 60000).
        self.max_connections = {
            'public': AsyncLimiter(20, 60000 / 1000),
            'private': AsyncLimiter(0, 0 / 1000)
        }
        self.ws_endpoint = {
            'public': 'wss://api-pub.bitfinex.com/ws/2',
            'private': 'wss://api.bitfinex.com/ws/2'
        }
        self.event = 'event'
        self.subscribed = 'subscribed'
        # All message events that are not unified.
        self.others = ['info']

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'event': 'subscribe',
             'channel': ex_name,
             'symbol': id}.update(params)
            for id in ids
        ]

    async def subscribe_order_book(self, symbols):
        params = {
            'prec': 'P0',
            'freq': 'F0',
            'len': 100
        }
        requests = self.build_requests(symbols, self.ORDER_BOOK, params)
        await self.subscription_handler(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, timeframe='1m'):
        ex_timeframe = self.timeframes[timeframe]
        params = {'key': 'trade:' + ex_timeframe + ':' + id}
        requests = self.build_requests(symbols, self.OHLCVS, params)
        await self.subscription_handler(requests, public=True)

    def ex_channel_id_from_reply(self, reply):
        if isinstance(reply, dict):
            return reply['chanId']
        elif isinstance(reply, list):
            return reply[0]
        else:
            raise UnknownResponse(reply)

    def parse_subscribed(self, reply, websocket, market=None):
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
        if name == self.channels[self.ORDER_BOOK]['ex_name']:
            result = {
                'prec': reply['prec'],
                'freq': reply['freq'],
                'len': int(reply['len'])
            }
            channel.update(result)
            channel['request'].update(result)
        else:
            id = reply['symbol']
            channel['request'].update({'symbol': id})
            symbol = self.markets_by_id[id]['symbol']
            channel.update({'symbol': symbol})
            if name == self.channels[self.OHLCVS]['ex_name']:
                key = reply['key']
                channel['request'].update({'key': key})
                _, timeframe, id = key.split(sep=':')[:3]
                symbol = self.markets_by_id[id]['symbol']
                channel.update({
                    'symbol': symbol,
                    'timeframe': timeframe
                })
        self.connection_metadata_handler(websocket, channel)

    def parse_error(self, reply, websocket, market=None):
        code = reply['code'] if self.key_exists(reply, 'code') else None
        if reply['event'] == 'error':
            if code == 10000:
                raise BaseError('Unknown event.')
            elif code == 10001:
                raise ExchangeError('Unknown pair.')
            elif code == 10300:
                raise SubscribeError
            elif code == 10301:
                raise SubscribeError('Already subscribed.')
            elif code == 10302:
                raise SubscribeError('Unknown channel.')
            elif code == 10305:
                raise ChannelLimitExceeded
            elif code == 10400:
                raise UnsubscribeError
            elif code == 10401:
                raise UnsubscribeError('Not subscribed.')
        elif reply['event'] == 'info':
            if super().key_exists(reply, 'version'):
                if reply['version'] == 2:
                    pass
                else:
                    raise NetworkError('Version number changed.')
            elif code == 20051:
                raise Reconnect('Unsubscribe/subscribe to all channels.')
            elif code == 20060:
                raise OnMaintenance(
                    'Exchange is undergoing maintenance.'
                    + ' Pause activity for 2 minutes and then'
                    + ' unsubscribe/subscribe all channels.'
                )
        else:
            raise BaseError(reply['msg'])

    def parse_ticker(self, reply, websocket, market=None):
        ticker = reply[1]
        return self.TICKER, super().parse_ticker(ticker, market)

    def parse_trades(self, reply, websocket, market=None):
        trades = reply[1]
        if not isinstance(trades[0], list):
            trades = [trades]
        trades = self.sort_by(trades, 1)  # Sort by timestamp
        return self.TRADES, [self.parse_trade(t, market=market) for t in trades]

    def parse_order_book(self, reply, websocket, market=None):
        order_book = reply[1]
        symbol = market['symbol']
        priceIndex = 1
        if not isinstance(order_book[0], list):
            order_book = [order_book]
        for i in range(0, len(order_book)):
            order = order_book[i]
            price = order[priceIndex]
            side = 'bids' if (order[2] > 0) else 'asks'
            amount = abs(order[2])
            self.order_book[symbol][side].append([price, amount])
        timeframe = self.milliseconds()
        self.order_book[symbol].update({
            'timeframe': timeframe,
            'datetime': self.iso8601(timeframe),
            'nonce': None
        })
        self.order_book[symbol]['bids'] = sorted(self.order_book[symbol]['bids'], key=lambda l: l[0], reverse=True)
        self.order_book[symbol]['asks'] = sorted(self.order_book[symbol]['asks'], key=lambda l: l[0])
        return self.ORDER_BOOK, {symbol: self.order_book[symbol]}

    def parse_ohlcvs(self, reply, websocket, market=None):
        ohlcvs = reply[1]
        symbol = market['symbol']
        if not isinstance(ohlcvs[0], list):
            ohlcvs = [ohlcvs]
        ohlcvs = [[i[0], i[1], i[3], i[4], i[2], i[5]] for i in ohlcvs]
        return self.OHLCVS, {symbol: self.sort_by(ohlcvs, 0)}
