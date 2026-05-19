"""
Deposit Wallet Manager for POLY_1271 signature type 3.
Uses the relay client to deploy the deposit wallet if needed.
"""
import os
import sys
sys.path.insert(0, '/Users/kenrickowen/Documents/POLY_HFT')

from dotenv import load_dotenv
load_dotenv('/Users/kenrickowen/Documents/POLY_HFT/.env')

from eth_account import Account
from eth_keys import keys
from py_builder_relayer_client.client import RelayClient
from py_builder_relayer_client.signer import Signer
from py_builder_signing_sdk.config import BuilderConfig
from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds

RELAYER_URL = "https://relayer.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet


def derive_deposit_wallet_address(owner_address: str) -> str:
    """Derive the deposit wallet address from the owner's EOA."""
    from py_builder_relayer_client.builder.derive import derive
    from py_builder_relayer_client.config import get_contract_config
    config = get_contract_config(CHAIN_ID)
    return derive(owner_address, config.safe_factory)


def main():
    private_key = os.getenv("PRIVATE_KEY", "")
    relayer_api_key = os.getenv("RELAYER_API_KEY", "")
    relayer_api_secret = os.getenv("RELAYER_API_SECRET", "")
    relayer_api_passphrase = os.getenv("RELAYER_API_PASSPHRASE", "")

    if not private_key:
        print("ERROR: PRIVATE_KEY not set in .env")
        return

    # Get owner address from private key
    account = Account.from_key(private_key)
    owner_address = account.address
    print(f"Owner (EOA) address: {owner_address}")

    # Derive expected deposit wallet address
    deposit_wallet_address = derive_deposit_wallet_address(owner_address)
    print(f"Expected deposit wallet address: {deposit_wallet_address}")

    # Build builder config if relayer credentials provided
    builder_config = None
    if relayer_api_key and relayer_api_secret and relayer_api_passphrase:
        builder_creds = BuilderApiKeyCreds(
            key=relayer_api_key,
            secret=relayer_api_secret,
            passphrase=relayer_api_passphrase,
        )
        builder_config = BuilderConfig(local_builder_creds=builder_creds)
        print("Builder credentials configured")
    else:
        print("Note: RELAYER_API_KEY/ SECRET/ PASSPHRASE not set — will derive address only")

    # Create signer
    signer = Signer(private_key=private_key, chain_id=CHAIN_ID)
    print(f"Signer created for: {signer.address()}")

    # Create relay client
    relay_client = RelayClient(
        relayer_url=RELAYER_URL,
        chain_id=CHAIN_ID,
        private_key=private_key,
        builder_config=builder_config,
    )

    # Check if deposit wallet is already deployed
    deployed = relay_client.get_deployed(deposit_wallet_address)
    print(f"Deposit wallet deployed: {deployed}")

    if deployed:
        print(f"\n=== ALREADY DEPLOYED ===")
        print(f"Deposit wallet address: {deposit_wallet_address}")
        print(f"\nUpdate your .env FUNDER_ADDRESS to:")
        print(f"  FUNDER_ADDRESS={deposit_wallet_address}")
    else:
        if not builder_config:
            print("\nCannot deploy without builder credentials.")
            print("Get your builder API key from Polymarket Builders dashboard.")
            return
        print("\nDeploying deposit wallet now...")
        try:
            result = relay_client.deploy()
            print(f"Deposit wallet deployed! Result: {result}")
        except Exception as e:
            print(f"Deploy failed: {e}")
            return

    print(f"\n=== NEXT STEPS ===")
    print(f"1. Update FUNDER_ADDRESS in .env to:")
    print(f"   FUNDER_ADDRESS={deposit_wallet_address}")
    print(f"2. Transfer pUSD to this deposit wallet address on Polygon")
    print(f"3. Run your trading bot again")


if __name__ == "__main__":
    main()