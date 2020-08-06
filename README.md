# cryptoapi

Asynchronous cryptocurrency REST and websocket API with support for multiple exchanges.

Cryptoapi is built on top of the fantastic [CCXT](github.com/ccxt/ccxt) library.
If you plan to do any serious trading, I would recommend paying for access to [CCXT Pro](ccxt.pro) because cryptoapi is still in development.

## Installation

Cryptoapi is available on PyPI.

It is recommended to use the `--user` flag on package installations. Drop the flag if installing cryptoapi system-wide.
```
pip install --user cryptoapi
```

## Usage

The API currently supports Bitfinex (API version 2), Bitvavo, Coinbase Pro, and Kraken.

### Unified Methods

Each exchange has four unified websocket methods in addition to the REST methods provided by [CCXT](github.com/ccxt/ccxt).
All results are formatted the same as in the CCXT library.

All of the methods put the results received from the exchange in the `exchange_instance.result` asyncio queue.
The results can be retrieved by using the `.get()` corountine method on the queue.

* `subscribe_ticker`: ticker as a dictionary.
* `subscribe_trades`: a list of trades recieved from the exchange.
* `subscribe_ohlcvs`: a list of `[timestamp, open, high, low, close, volume]` candles, often just one candle is present (the candle for the timeframe provided, which is one minute by default).
* `subscribe_order_book`: the data sent to the queue is the update from the exchange. Cryptoapi automatically keeps an updated order book for every instance (see the Local Order Book section below).

### Example

Note that `asyncio` must be available to take advantage of asynchronous capabilities.
The results from the exchanges are stored in the `exchange.result` `asyncio` queue in the form of `(channel, data)` tuples.
The `channel` in this example is `'order_book'`. The data is the reply from the exchange. 
```python
import asyncio
import cryptoapi


async def main():
    exchanges = [
        cryptoapi.Bitfinex(),
    ]
    for exchange in exchanges:
        await exchange.load_markets()
    symbols = ['BTC/EUR', 'ETH/EUR']
    tasks = [
        asyncio.create_task(exchange.subscribe_order_book(symbols))
        for exchange in exchanges
    ]
    tasks.append(asyncio.create_task(get_results(exchanges, symbols)))
    for t in tasks:
        await t
    for exchange in exchanges:
        exchange.close()


async def get_results(exchanges, symbols):
    while True:
        for exchange in exchanges:
            for symbol in symbols:
                if symbol in exchange.symbols:
                    channel, data = await exchange.result.get()
                    print(data)


if __name__ == "__main__":
    asyncio.run(main())
```

### Local Order Book

If you subscribe to an order book channel, cryptoapi will keep a local copy of the order book in the `exchange.order_book` dictionary.
Keep in mind that this dictionary is tied to the exchange instance, so if you have multiple instances of the same exchange you will also have multiple order books.
An example structure of the dictionary is outlined below.
```python
{
    'BTC/USD': {
        'bids': [[11111, 1.7], ...]             # [price, amount] sorted by price in descending order (best bid first).    
        'asks': [[11112, 3], ...]               # [price, amount] sorted by price in ascending order (best ask first).
        'timestamp': 1596729013,                # Unix timestamp for when the book was last updated.
        'datetime': '2020-08-06T15:50:56.714Z', # iso860 datetime. Computed from the timestamp property.
        'nonce': 109335233,                     # Exchange-provided nonce. None if not provided.
    },
    ...
}
```
