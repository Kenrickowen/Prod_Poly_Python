"""On-chain redemption for resolved Polymarket CTF positions."""
from __future__ import annotations

import logging
import os
import ssl
import time
from dataclasses import dataclass

import certifi
import requests
from eth_account import Account
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from web3 import Web3
from web3.exceptions import ContractLogicError

from polymarket_python.config import (
    CHAIN_ID,
    INFURA_URL,
    POLYMARKET_CTF,
    POLYMARKET_CTF_COLLATERAL_ADAPTER,
    POLYMARKET_NEG_RISK_CTF_COLLATERAL_ADAPTER,
    POLYMARKET_USDCE,
    REDEMPTION_GAS_LIMIT,
    REDEMPTION_MAX_GAS_GWEI,
)

logger = logging.getLogger(__name__)

ZERO_BYTES32 = b"\x00" * 32
BINARY_INDEX_SETS = [1, 2]


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


CTF_ABI = [
    {
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "id", "type": "uint256"},
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "name": "isApprovedForAll",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "payoutDenominator",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

CTF_COLLATERAL_ADAPTER_ABI = [
    {
        "inputs": [
            {"name": "", "type": "address"},
            {"name": "", "type": "bytes32"},
            {"name": "_conditionId", "type": "bytes32"},
            {"name": "", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@dataclass
class RedemptionResult:
    attempted: bool
    redeemed: bool
    tx_hash: str = ""
    reason: str = ""
    balance_up_raw: int = 0
    balance_down_raw: int = 0


class PolymarketRedeemer:
    """Redeem resolved binary CTF positions held by the configured EOA."""

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        private_key: str | None = None,
        funder_address: str | None = None,
    ):
        self.rpc_url = rpc_url or os.getenv("INFURA_URL", "") or INFURA_URL
        self.private_key = private_key or os.getenv("PRIVATE_KEY", "")
        self.funder_address = Web3.to_checksum_address(funder_address or os.getenv("FUNDER_ADDRESS", ""))

        if not self.rpc_url:
            raise ValueError("INFURA_URL is required for redemption")
        if not self.private_key:
            raise ValueError("PRIVATE_KEY is required for redemption")

        self.account = Account.from_key(self.private_key)
        self.signer_address = Web3.to_checksum_address(self.account.address)
        if self.signer_address.lower() != self.funder_address.lower():
            raise ValueError("Direct redemption requires PRIVATE_KEY to control FUNDER_ADDRESS")

        session = _make_ssl_session()
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, session=session))
        if not self.w3.is_connected():
            raise ConnectionError("Could not connect to Polygon RPC")

        self.ctf_address = Web3.to_checksum_address(POLYMARKET_CTF)
        self.standard_adapter_address = Web3.to_checksum_address(POLYMARKET_CTF_COLLATERAL_ADAPTER)
        self.neg_risk_adapter_address = Web3.to_checksum_address(POLYMARKET_NEG_RISK_CTF_COLLATERAL_ADAPTER)
        self.usdce_address = Web3.to_checksum_address(POLYMARKET_USDCE)
        self.ctf = self.w3.eth.contract(address=self.ctf_address, abi=CTF_ABI)
        self.standard_adapter = self.w3.eth.contract(
            address=self.standard_adapter_address,
            abi=CTF_COLLATERAL_ADAPTER_ABI,
        )
        self.neg_risk_adapter = self.w3.eth.contract(
            address=self.neg_risk_adapter_address,
            abi=CTF_COLLATERAL_ADAPTER_ABI,
        )

    def _condition_bytes(self, condition_id: str) -> bytes:
        if not condition_id.startswith("0x") or len(condition_id) != 66:
            raise ValueError(f"Invalid condition_id: {condition_id}")
        return bytes.fromhex(condition_id[2:])

    def is_resolved(self, condition_id: str) -> bool:
        condition = self._condition_bytes(condition_id)
        return int(self.ctf.functions.payoutDenominator(condition).call()) > 0

    def get_balances(self, token_id_up: str, token_id_down: str) -> tuple[int, int]:
        up = self.ctf.functions.balanceOf(self.funder_address, int(token_id_up)).call()
        down = self.ctf.functions.balanceOf(self.funder_address, int(token_id_down)).call()
        return int(up), int(down)

    def _build_tx(self, fn, *, gas_limit: int | None = None) -> dict:
        nonce = self.w3.eth.get_transaction_count(self.signer_address, "pending")
        tx = fn.build_transaction(
            {
                "from": self.signer_address,
                "chainId": CHAIN_ID,
                "nonce": nonce,
                "gas": gas_limit or REDEMPTION_GAS_LIMIT,
            }
        )
        latest = self.w3.eth.get_block("latest")
        if "baseFeePerGas" in latest:
            max_priority = self.w3.to_wei(35, "gwei")
            max_fee = min(
                int(latest["baseFeePerGas"] * 2 + max_priority),
                self.w3.to_wei(REDEMPTION_MAX_GAS_GWEI, "gwei"),
            )
            tx["maxPriorityFeePerGas"] = max_priority
            tx["maxFeePerGas"] = max_fee
        else:
            tx["gasPrice"] = min(
                self.w3.eth.gas_price,
                self.w3.to_wei(REDEMPTION_MAX_GAS_GWEI, "gwei"),
            )
        return tx

    def _send_tx(self, fn, *, gas_limit: int | None = None) -> str:
        tx = self._build_tx(fn, gas_limit=gas_limit)
        try:
            estimated = fn.estimate_gas({"from": self.signer_address})
            tx["gas"] = min(max(int(estimated * 1.25), 100_000), gas_limit or REDEMPTION_GAS_LIMIT)
        except ContractLogicError:
            raise
        except Exception as e:
            logger.debug("[REDEEM] Gas estimate failed; using configured gas: %s", e)

        signed = self.account.sign_transaction(tx)
        raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
        return tx_hash.hex()

    def _ensure_approval(self, adapter_address: str) -> str:
        approved = self.ctf.functions.isApprovedForAll(self.funder_address, adapter_address).call()
        if approved:
            return ""
        logger.info("[REDEEM] Approving adapter %s for CTF transfers", adapter_address)
        fn = self.ctf.functions.setApprovalForAll(adapter_address, True)
        tx_hash = self._send_tx(fn, gas_limit=120_000)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt.status != 1:
            raise RuntimeError(f"CTF approval failed: {tx_hash}")
        return tx_hash

    def redeem(
        self,
        *,
        condition_id: str,
        token_id_up: str,
        token_id_down: str,
        neg_risk: bool = False,
        wait_for_receipt: bool = False,
    ) -> RedemptionResult:
        """Redeem all held UP/DOWN balances for a resolved condition."""
        if not condition_id:
            return RedemptionResult(False, False, reason="missing condition_id")

        condition = self._condition_bytes(condition_id)
        if not self.is_resolved(condition_id):
            return RedemptionResult(False, False, reason="condition not resolved")

        balance_up, balance_down = self.get_balances(token_id_up, token_id_down)
        if balance_up <= 0 and balance_down <= 0:
            return RedemptionResult(
                False,
                False,
                reason="no CTF token balance to redeem",
                balance_up_raw=balance_up,
                balance_down_raw=balance_down,
            )

        adapter = self.neg_risk_adapter if neg_risk else self.standard_adapter
        adapter_address = self.neg_risk_adapter_address if neg_risk else self.standard_adapter_address
        approval_tx = self._ensure_approval(adapter_address)
        if approval_tx:
            logger.info("[REDEEM] Approval confirmed: %s", approval_tx)

        fn = adapter.functions.redeemPositions(
            self.usdce_address,
            ZERO_BYTES32,
            condition,
            BINARY_INDEX_SETS,
        )
        tx_hash = self._send_tx(fn)
        if wait_for_receipt:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            if receipt.status != 1:
                raise RuntimeError(f"Redemption transaction failed: {tx_hash}")

        logger.info(
            "[REDEEM] Submitted redemption tx=%s condition=%s balances=(%s,%s)",
            tx_hash,
            condition_id,
            balance_up,
            balance_down,
        )
        return RedemptionResult(
            True,
            True,
            tx_hash=tx_hash,
            reason="submitted",
            balance_up_raw=balance_up,
            balance_down_raw=balance_down,
        )


def now_ms() -> int:
    return int(time.time() * 1000)
