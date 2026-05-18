"""Read-only Polygon wallet balance helpers for dashboard display."""
from __future__ import annotations

import os
import ssl
import time
from dataclasses import dataclass

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from web3 import Web3

from polymarket_python.config import INFURA_URL, POLYMARKET_PUSD, POLYMARKET_USDC, POLYMARKET_USDCE


class _SSLAdapter(HTTPAdapter):
    def __init__(self, ssl_ctx, **kwargs):
        self.ssl_ctx = ssl_ctx
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(
            ssl_context=self.ssl_ctx,
            num_pools=connections,
            maxsize=maxsize,
            block=block,
        )


def _make_ssl_session() -> requests.Session:
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(certifi.where())
    session = requests.Session()
    session.mount("https://", _SSLAdapter(ctx))
    return session


ERC20_BALANCE_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass
class WalletBalances:
    address: str
    pol: float
    usdc: float
    usdce: float
    pusd: float
    timestamp_ms: int


class WalletBalanceClient:
    """Read native POL, USDC.e, and Polymarket pUSD balances via Polygon RPC."""

    def __init__(self, *, rpc_url: str | None = None, wallet_address: str | None = None):
        self.rpc_url = rpc_url or os.getenv("INFURA_URL", "") or INFURA_URL
        self.wallet_address = wallet_address or os.getenv("FUNDER_ADDRESS", "")

        if not self.rpc_url:
            raise ValueError("INFURA_URL is required to read wallet balances")
        if not self.wallet_address:
            raise ValueError("FUNDER_ADDRESS is required to read wallet balances")

        session = _make_ssl_session()
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, session=session))
        if not self.w3.is_connected():
            raise ConnectionError("Could not connect to Polygon RPC")

        self.wallet_address = Web3.to_checksum_address(self.wallet_address)
        self.usdce = self.w3.eth.contract(
            address=Web3.to_checksum_address(POLYMARKET_USDCE),
            abi=ERC20_BALANCE_ABI,
        )
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(POLYMARKET_USDC),
            abi=ERC20_BALANCE_ABI,
        )
        self.pusd = self.w3.eth.contract(
            address=Web3.to_checksum_address(POLYMARKET_PUSD),
            abi=ERC20_BALANCE_ABI,
        )
        self._usdc_decimals: int | None = None
        self._usdce_decimals: int | None = None
        self._pusd_decimals: int | None = None

    def fetch(self) -> WalletBalances:
        pol_raw = self.w3.eth.get_balance(self.wallet_address)
        usdc_raw = self.usdc.functions.balanceOf(self.wallet_address).call()
        usdce_raw = self.usdce.functions.balanceOf(self.wallet_address).call()
        pusd_raw = self.pusd.functions.balanceOf(self.wallet_address).call()

        if self._usdc_decimals is None:
            self._usdc_decimals = int(self.usdc.functions.decimals().call())
        if self._usdce_decimals is None:
            self._usdce_decimals = int(self.usdce.functions.decimals().call())
        if self._pusd_decimals is None:
            self._pusd_decimals = int(self.pusd.functions.decimals().call())

        return WalletBalances(
            address=self.wallet_address,
            pol=float(self.w3.from_wei(pol_raw, "ether")),
            usdc=usdc_raw / (10 ** self._usdc_decimals),
            usdce=usdce_raw / (10 ** self._usdce_decimals),
            pusd=pusd_raw / (10 ** self._pusd_decimals),
            timestamp_ms=int(time.time() * 1000),
        )
