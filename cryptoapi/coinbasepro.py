import asyncio
import ccxt.async_support as ccxt
import exchange
from ccxt.base.errors import BaseError
from websockets_api.errors import UnknownResponse


class Coinbasepro(exchange.Exchange, ccxt.coinbasepro):

    def __init__(self, params={}):
        super(ccxt.coinbasepro, self).__init__(params)
        self.channels = {
            super().TICKER: {
                'ex_name': 'ticker',
                'has': True
            },
            super().TRADES: {
                'ex_name': 'matches',
                'has': True
            },
            super().ORDER_BOOK: {
                'ex_name': 'level2',
                'has': True
            },
            super().OHLCVS: {
                'ex_name': '',
                'has': False
            }
        }
        self.channels_by_ex_name = {
            v['ex_name']: {
                'name': symbol,
                'has': v['has']
            }
            for symbol, v in self.channels.items()
        }
        self.max_channels = 1000000  # Maximum number of channels per connection. No limit for coinbasepro
        self.max_connections = {'public': (1, 4000), 'private': (0, 0)}
        self.connections = {}
        self.pending_channels = {}
        self.result = asyncio.Queue(maxsize=1)
        self.ws_endpoint = {
            'public': 'wss://ws-feed.pro.coinbase.com',
            'private': ''
        }
        self.event = 'type'
        self.events = {
            self.parse_subscribed: ['subscriptions'],
            self.parse_unsubscribed: ['unsubscribed'],
            self.parse_error: ['error'],
            self.parse_other: [],
            self.parse_ticker: ['ticker'],
            self.parse_trades: ['matches'],
            self.parse_order_book: ['snapshot', 'level2'],
            self.parse_ohlcvs: []
        }
        self.order_book = {}

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'type': 'subscribe',
             'channels': [{'name': ex_name, 'product_ids': [id]}]}.update(params)
            for id in ids
        ]

    async def build_unsubscribe_request(self, channel):
        return {
            'type': 'unsubscribe',
            'product_ids': channel['ex_channel_id'][0],
            'channels': [channel['ex_channel_id'][1]]
        }

    async def subscribe_ticker(self, symbols, params={}):
        requests = self.build_requests(symbols, super().TICKER)
        await self.subscription_handler(requests, public=True)

    async def subscribe_trades(self, symbols, params={}):
        requests = self.build_requests(symbols, super().TRADES)
        await self.subscription_handler(requests, public=True)

    async def subscribe_order_book(self, symbols, params={}):
        requests = self.build_requests(symbols, super().ORDER_BOOK)
        await self.subscription_handler(requests, public=True)

    def parse_subscribed(self, reply, websocket, market=None):
        ex_name = reply['channels'][0]['name']
        subed_ids = reply['channels'][0]['product_ids']  # List of subscribed markets
        subed_symbols = [
            c['symbol']
            for _, v in self.connections.items()
            for ws, channels in v.items()
            for c in channels
        ]  # List of subscribed and registered markets
        id, symbol = [
            (id, self.markets_by_id[id]['symbol'])
            for id in subed_ids
            if self.markets_by_id[id]['symbol'] not in subed_symbols
        ][0]  # Find the only subed id that isn't registered yet
        name = self.channels_by_ex_name[ex_name]['name']
        request = {
            'type': 'subscribe',
            'product_ids': [id],
            'channels': [{'name': ex_name, 'product_ids': [id]}]
        }
        channel = {
            'request': request,
            'channel_id': self.claim_channel_id(),
            'name': name,
            'symbol': symbol,
            'ex_channel_id': (ex_name, id)
        }
        self.connection_metadata_handler(websocket, channel)

    def parse_unsubscribed(self, reply, websocket, market=None):
        for c in exchange.Exchange.get_channels(self.connections):
            if c['ex_channel_id'] == (reply['product_ids'], reply['channels']):
                channel = c
                del c  # Unregister the channel
                return {'unsubscribed': channel['channel_id']}

    def parse_error(self, reply, websocket, market=None):
        err = f"Error: {reply['message']}."
        reason = f"Reason: {reply['reason']}" if super().key_exists(reply, 'reason') else ''
        raise BaseError(err + "\n" + reason)

    def parse_ticker(self, reply, websocket, market=None):
        ticker = reply
        return super().TICKER, super().parse_ticker(ticker, market)

    def parse_trades(self, reply, websocket, market=None):
        trade = reply
        return super().TRADES, [super().parse_trade(trade, market=market)]

    def parse_order_book(self, reply, websocket, market=None):
        order_book = reply
        symbol = market['symbol']
        if order_book['type'] == 'snapshot':
            order_book = super().parse_order_book(order_book)
            self.order_book[symbol] = {'bids': order_book['bids'], 'asks': order_book['asks']}
        else:
            for change in order_book['changes']:
                self_order_book = self.order_book[symbol]['bids'] if 'buy' in change else self.order_book[symbol]['asks']
                price = float(change[1])
                amount = float(change[2])
                existing_prices = [o[0] for o in self_order_book]
                if price in existing_prices:
                    idx = existing_prices.index(price)
                    if amount == 0:
                        del self_order_book[idx]
                    else:
                        self_order_book[idx] = [price, amount]
                else:
                    self_order_book.append([price, amount])
        timeframe = self.milliseconds()
        self.order_book[symbol].update({
            'timeframe': timeframe,
            'datetime': self.iso8601(timeframe),
            'nonce': None
        })
        self.order_book[symbol]['bids'] = sorted(self.order_book[symbol]['bids'], key=lambda l: l[0], reverse=True)
        self.order_book[symbol]['asks'] = sorted(self.order_book[symbol]['asks'], key=lambda l: l[0])
        return super().ORDER_BOOK, {symbol: self.order_book[symbol]}
