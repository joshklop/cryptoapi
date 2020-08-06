import ccxt.async_support as ccxt
import cryptoapi.base.exchange as exchange

from ccxt.base.errors import BaseError
from aiolimiter import AsyncLimiter


class Coinbasepro(exchange.Exchange, ccxt.coinbasepro):

    def __init__(self, config={}):
        ccxt.coinbasepro.__init__(self, config=config)
        exchange.Exchange.__init__(self)
        self.channels[self.TICKER]['ex_name'] = 'ticker'
        self.channels[self.TRADES]['ex_name'] = 'matches'
        self.channels[self.ORDER_BOOK]['ex_name'] = 'level2'
        self.channels[self.TICKER]['has'] = True
        self.channels[self.TRADES]['has'] = True
        self.channels[self.ORDER_BOOK]['has'] = True
        self.channels_by_ex_name = self.create_channels_by_ex_name()
        # Maximum number of channels per connection.
        # Unlimited if equal to 10 ** 5.
        self.max_channels = 10 ** 5
        # Number of connections that can be created per unit time,
        #   where the unit of time is in milliseconds.
        # Example: AsyncLimiter(1, 60000 / 1000) --> one connection per minute
        # Unlimited if equal to (10 ** 5, 60000).
        self.max_connections = {
            'public': AsyncLimiter(1, 4000 / 1000),
            'private': AsyncLimiter(1, 60000 / 1000)
        }
        self.ws_endpoint = {
            'public': 'wss://ws-feed.pro.coinbase.com',
            'private': ''
        }
        self.event = 'type'
        self.subscribed = 'subscriptions'

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'type': 'subscribe',
             'channels': [{'name': ex_name, 'product_ids': [id]}],
             **params}
            for id in ids
        ]

    def ex_channel_id_from_reply(self, reply):
        if reply['type'] in ['snapshot', 'l2update']:
            name = self.channels[self.ORDER_BOOK]['ex_name']
        elif reply['type'] in ['last_match', 'match']:
            name = 'matches'
        else:
            name = reply['type']
        return (name, reply['product_id'])

    def register_channel(self, reply, websocket):
        ex_name = reply['channels'][0]['name']
        name = self.channels_by_ex_name[ex_name]['name']
        subed_ids = reply['channels'][0]['product_ids']  # List of subscribed markets
        id, symbol = self.find_not_subbed_symbol(subed_ids)
        request = {
            'type': 'subscribe',
            'channels': [{'name': ex_name, 'product_ids': [id]}]
        }
        channel = {
            'request': request,
            'channel_id': self.claim_channel_id(),
            'ex_channel_id': (ex_name, id),
            'name': name,
            'symbol': symbol,
        }
        self.connections[websocket].append(channel)  # Register channel

    def parse_error_ws(self, reply, market=None):
        err = f"Error: {reply['message']}."
        reason = f"Reason: {reply['reason']}" if super().key_exists(reply, 'reason') else ''
        raise BaseError(err + "\n" + reason)

    def parse_ticker_ws(self, reply, market):
        return self.TICKER, super().parse_ticker(reply, market)

    def parse_trades_ws(self, reply, market):
        return self.TRADES, [self.parse_trade(reply, market)]

    def parse_order_book_ws(self, reply, market):
        if reply['type'] == 'snapshot':
            snapshot = True
            update = super().parse_order_book(reply)
        else:
            snapshot = False
            update = {
                'bids': [],
                'asks': [],
                'timestamp': None,
                'datetime': None,
                'nonce': None
            }
            for o in reply['changes']:
                side = 'bids' if o[0] == 'buy' else 'asks'
                price = float(o[1])
                amount = float(o[2])
                update[side].append([price, amount])
        self.update_order_book(update, market, snapshot)
        return 'order_book', {market['symbol']: update}
