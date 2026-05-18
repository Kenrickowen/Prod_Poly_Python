#!/usr/bin/env python3
"""Run the Polymarket BTC 5m Breakout trading bot."""
import sys
import os
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env", override=True)

from polymarket_python.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
