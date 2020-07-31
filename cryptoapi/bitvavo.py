import ccxt.async_support as ccxt
import exchange
from aiolimiter import AsyncLimiter


class Bitvavo(exchange.Exchange, ccxt.bitvavo):

    def __init__(self, params={}):
        super(ccxt.bitvavo, self).__init__(params)
        super(exchange.Exchange, self).__init__()
        self.channels[self.TICKER]['ex_name'] = 'ticker24h'
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
        self.max_channels = 10 ** 5
        # Number of connections that can be created per unit time,
        #   where the unit of time is in milliseconds.
        # Example: AsyncLimiter(1, 60000 / 1000) --> one connection per minute
        # Unlimited if equal to (10 ** 5, 60000).
        self.max_connections = {
            'public': AsyncLimiter(10 ** 5, 60000 / 1000),
            'private': AsyncLimiter(0, 0 / 1000)
        }
        self.ws_endpoint = {
            'public': 'wss://ws.bitvavo.com/v2/',
            'private': ''
        }
        self.event = 'event'
        self.subscribed = 'subscribe'
        # All message events that are not unified.
        self.others = ['unsubscribed']

    def build_requests(self, symbols, name, params={}):
        ids = [self.markets[s]['id'] for s in symbols]
        ex_name = self.channels[name]['ex_name']
        return [
            {'action': 'subscribe',
             'channels': [{'name': ex_name, 'markets': [id]}.update(params)]}
            for id in ids
        ]

    def ex_channel_id_from_reply(self, reply):
        return (reply['event'], reply['market'])

    def update_connections(self, reply, websocket):
        ex_name = list(reply.keys())[0]
        name = self.channels_by_ex_name[ex_name]['name']
        if name == self.OHLCVS:
            ex_timeframe = reply[ex_name]
            timeframe = self.timeframes[ex_timeframe]
            params = {'interval': ex_timeframe}
            id = reply[ex_name][timeframe][0]
        else:
            id = reply[ex_name][0]
        symbol = self.markets[id]['symbol']
        request = self.build_request([symbol], name, params)
        channel = {
            'request': request,
            'channel_id': self.claim_channel_id(),
            'name': name,
            'symbol': symbol,
            'ex_channel_id': (ex_name, id)
        }
        self.connection_metadata_handler(websocket, channel)

    def parse_error_ws(self, reply, market):
        pass  # Errors are not defined in API documentation.

    def parse_ticker_ws(self, reply, market):
        return self.TICKER, super().parse_ticker(reply, market)

    def parse_trades_ws(self, reply, market):
        return self.TRADES, [super().parse_trade(reply, market)]

    def parse_order_book_ws(self, reply, market):
        snapshot = True if reply['nonce'] == 0 else False
        update = super().parse_order_book(reply)
        self.update_order_book(update, market, snapshot)
        return 'order_book', {market['symbol']: update}

    def parse_ohlcvs_ws(self, reply, market):
        return self.OHLCVS, super().parse_ohlcvs(reply, market)
