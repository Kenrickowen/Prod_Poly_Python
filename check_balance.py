#!/usr/bin/env python3
"""Check Polymarket wallet balance using Infura RPC."""

import os
import sys
from pathlib import Path

try:
    from web3 import Web3
except ImportError:
    print("Installing web3...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "web3"])
    from web3 import Web3

def load_env():
    env_path = Path(__file__).parent / ".env"
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

def main():
    load_env()

    address = os.getenv("FUNDER_ADDRESS", "").strip()
    if not address:
        print("Error: FUNDER_ADDRESS not set in .env")
        sys.exit(1)

    # Check if INFURA_URL is in .env
    infura_url = os.getenv("INFURA_URL", "").strip()
    if not infura_url:
        print("Error: INFURA_URL not set in .env")
        print("Add: INFURA_URL=https://polygon-mainnet.infura.io/v3/YOUR_PROJECT_ID")
        sys.exit(1)

    print(f"Checking balance for: {address}")
    print(f"RPC: Infura\n")

    try:
        w3 = Web3(Web3.HTTPProvider(infura_url))
        print(f"Connected: {w3.is_connected()}")

        if w3.is_connected():
            balance_wei = w3.eth.get_balance(address)
            balance_pol = round(balance_wei / 1e18, 6)
            print(f"POL Balance: {balance_pol}")
        else:
            print("Failed to connect")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"\nView on Polygon explorer: https://polygonscan.com/address/{address}")

if __name__ == "__main__":
    main()