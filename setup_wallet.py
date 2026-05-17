#!/usr/bin/env python3
"""Initialize and validate Polymarket trading wallet."""

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

# Load .env file
def load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print("Error: .env file not found")
        sys.exit(1)

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

def main():
    load_env()

    private_key = os.getenv("PRIVATE_KEY", "").strip()
    if not private_key:
        print("Error: PRIVATE_KEY not set in .env")
        sys.exit(1)

    if not private_key.startswith("0x") or len(private_key) != 66:
        print("Error: PRIVATE_KEY must be 64 hex characters with 0x prefix")
        sys.exit(1)

    # Derive address from private key
    account = Account.from_key(private_key)
    address = account.address

    print(f"Wallet Address: {address}")

    # Save address to .env if not set
    funder = os.getenv("FUNDER_ADDRESS", "").strip()
    if not funder:
        env_path = Path(__file__).parent / ".env"
        with open(env_path) as f:
            content = f.read()

        if "FUNDER_ADDRESS=" in content:
            content = content.replace("FUNDER_ADDRESS=", f"FUNDER_ADDRESS={address}")
        else:
            content = f"\nFUNDER_ADDRESS={address}\n"

        with open(env_path, "w") as f:
            f.write(content)

        print(f"Updated .env with FUNDER_ADDRESS")
    elif funder != address:
        print(f"Warning: FUNDER_ADDRESS mismatch!")
        print(f"  .env says:    {funder}")
        print(f"  Derived from key: {address}")

    print("\nWallet setup complete!")

if __name__ == "__main__":
    main()