import asyncio
import ccxt.async_support as ccxt
import exchange
from ccxt.base.errors import BaseError
from ccxt.base.errors import ExchangeError
from ccxt.base.errors import NetworkError
from ccxt.base.errors import OnMaintenance
from websockets_api.errors import SubscribeError
from websockets_api.errors import UnsubscribeError
from websockets_api.errors import ChannelLimitExceeded
from websockets_api.errors import Reconnect
from websockets_api.errors import UnknownResponse


class Bitfinex(exchange.Exchange, ccxt.bitfinex2):

    def __init__(self, params={}):
        super(exchange.Exchange, self).__init__(params)
        self.channels = {
            super().TICKER: {
                'ex_name': 'ticker',
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
        self.max_channels = 25  # Maximum number of channels per connection.
        self.max_connections = {'public': (20, 60000), 'private': (5, 15000)}
        self.connections = {}
        self.pending_channels = {}
        self.result = asyncio.Queue(maxsize=1)
        self.ws_endpoint = {
            'public': 'wss://api-pub.bitfinex.com/ws/2',
            'private': 'wss://api.bitfinex.com/ws/2'
        }
        self.order_book = {}

    async def build_unsubscribe_request(self, channel):
        return {
            'event': 'unsubscribe',
            'chanId': channel['ex_channel_id']
        }

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'event': 'subscribe',
             'channel': ex_name,
             'symbol': id}.update(params)
            for id in ids
        ]

    async def subscribe_ticker(self, symbols):
        requests = self.build_requests(symbols, super().TICKER)
        await self.subscription_handler(requests, public=True)

    async def subscribe_trades(self, symbols):
        requests = self.build_requests(symbols, super().TRADES)
        await self.subscription_handler(requests, public=True)

    async def subscribe_order_book(self, symbols, precision='P0',
                                   frequency='F0', depth=100):
        params = {
            'prec': precision,
            'freq': frequency,
            'len': depth
        }
        requests = self.build_requests(symbols, super().ORDER_BOOK, params)
        await self.subscription_handler(requests, public=True)

    async def subscribe_ohlcvs(self, symbols, timeframe='1m'):
        ex_timeframe = self.timeframes[timeframe]
        params = {'key': 'trade:' + ex_timeframe + ':' + id}
        requests = self.build_requests(symbols, super().OHLCVS, params)
        await self.subscription_handler(requests, public=True)

    def parse_reply(self, reply, websocket):
        event = reply['event']
        if isinstance(reply, dict):
            if event == 'subscribed':
                return self.parse_subscribed(reply, websocket)
            elif event == 'unsubscribed':
                return self.parse_unsubscribed(reply)
            elif event in ['info', 'error']:  # TODO info should go to different function
                return self.parse_error(reply)
            else:
                raise UnknownResponse(reply)
        elif isinstance(reply, list):
            channel_id = reply[0]
            # TODO sort self.connections by channel ids and do a binary search
            for c in super().get_channels(self.connections):
                if c['ex_channel_id'] == channel_id:
                    name = c['name']
                    symbol = c['symbol']
                    market = self.markets[symbol]
                    if name == super().TICKER:
                        return self.parse_ticker(reply[1], market)
                    elif name == super().TRADES:
                        reply = reply[1] if isinstance(reply[1], list) else reply[2]
                        return self.parse_trades(reply, market)
                    elif name == super().ORDER_BOOK:
                        return self.parse_order_book(reply[1], market, c['prec'])
                    elif name == super().OHLCVS:
                        return self.parse_ohlcvs(reply[1], market)
                    else:
                        raise UnknownResponse(reply)
        else:
            raise UnknownResponse(reply)

    def parse_subscribed(self, reply, websocket):
        channel = {}
        ex_name = reply['channel']
        name = self.channels_by_ex_name[ex_name]['name']
        channel.update({
            'request': {'event': 'subscribe', 'channel': ex_name}
        })
        channel.update({
            'channel_id': self.claim_channel_id(),
            'ex_channel_id': reply['chanId'],
            'name': name
        })
        if super().key_exists(reply, 'symbol'):
            id = reply['symbol']
            if super().key_exists(self.markets_by_id, id):
                symbol = self.markets_by_id[id]['symbol']
            else:
                return
            channel.update({'symbol': symbol})
            channel['request'].update({'symbol': id})
        elif super().key_exists(reply, 'key'):
            key = reply['key']
            _, timeframe, id = key.split(sep=':')[:3]
            if super().key_exists(self.markets_by_id, id):
                symbol = self.markets_by_id[id]['symbol']
            else:
                return
            channel.update({
                'symbol': symbol,
                'timeframe': timeframe
            })
            channel['request'].update({'key': key})
        if super().key_exists(reply, 'prec'):
            result = {
                'prec': reply['prec'],
                'freq': reply['freq'],
                'len': int(reply['len'])
            }
            channel.update(result)
            channel['request'].update(result)
        self.connection_metadata_handler(websocket, channel)

    def parse_unsubscribed(self, reply):
        for c in super().get_channels(self.connections):
            if c['ex_channel_id'] == reply['chanId']:
                channel = c
                del c  # Unregister the channel
                return {'unsubscribed': channel['channel_id']}

    def parse_error(self, reply):
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

    def parse_ticker(self, ticker, market):
        return super().TICKER, self.parse_ticker(ticker, market)

    def parse_trades(self, trades, market):
        if not isinstance(trades[0], list):
            trades = [trades]
        trades = self.sort_by(trades, 1)  # Sort by timestamp
        return super().TRADES, [self.parse_trade(t, market=market) for t in trades]

    def parse_order_book(self, orderbook, market, precision='R0'):
        # Mostly taken from ccxt.bitfinex2.parse_order_book
        # TODO find a way to use super().parse_order_book. There is a lot of repeated code here.
        symbol = market['symbol']
        priceIndex = 1 if (precision == 'R0') else 0
        if not isinstance(orderbook[0], list):
            orderbook = [orderbook]
        for i in range(0, len(orderbook)):
            order = orderbook[i]
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
        return super().ORDER_BOOK, {symbol: self.order_book[symbol]}

    def parse_ohlcvs(self, ohlcvs, market):
        symbol = market['symbol']
        if not isinstance(ohlcvs[0], list):
            ohlcvs = [ohlcvs]
        ohlcvs = [[i[0], i[1], i[3], i[4], i[2], i[5]] for i in ohlcvs]
        return super().OHLCVS, {symbol: self.sort_by(ohlcvs, 0)}
