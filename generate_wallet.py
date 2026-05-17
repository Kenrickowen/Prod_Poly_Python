#!/usr/bin/env python3
"""Generate a new Ethereum wallet for Polymarket trading."""

import os
import sys
from pathlib import Path

try:
    from eth_account import Account
except ImportError:
    print("Installing eth-account...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "eth-account"])
    from eth_account import Account

def main():
    # Generate new account
    account = Account.create()
    private_key = account.key.hex()
    address = account.address

    print("=" * 60)
    print("NEW WALLET GENERATED")
    print("=" * 60)
    print(f"\nAddress:    {address}")
    print(f"Private Key: {private_key}")
    print("\n" + "!" * 60)
    print("WARNING: Save the private key above - it cannot be recovered!")
    print("!" * 60)

    # Update .env
    env_path = Path(__file__).parent / ".env"
    with open(env_path) as f:
        content = f.read()

    content = content.replace("PRIVATE_KEY=", f"PRIVATE_KEY={private_key}")
    content = content.replace("FUNDER_ADDRESS=", f"FUNDER_ADDRESS={address}")

    with open(env_path, "w") as f:
        f.write(content)

    print(f"\nUpdated .env with new wallet details")
    print(f"\n⚠️  IMPORTANT: Back up your private key in a secure location!")

if __name__ == "__main__":
    main()