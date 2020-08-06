import pathlib
from setuptools import setup

HERE = pathlib.Path(__file__).parent

README = (HERE / 'README.md').read_text()

setup(
    name='cryptoapi',
    version='0.1.0',
    description='Asynchronous cryptocurrency REST and websocket API with support for multiple exchanges.',
    long_description=README,
    long_description_content_type='text/markdown',
    url='https://github.com/joshklop/cryptoapi',
    author='Josh Klopfenstein',
    author_email='joshklop@gmail.com',
    license='MIT',
    keywords='websocket rest api cryptocurrency exchange coinbasepro kraken bitvavo bitfinex',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
    ],
    packages=['cryptoapi'],
    include_package_data=True,
    install_requires=['aiolimiter', 'ccxt', 'websockets'],
)
