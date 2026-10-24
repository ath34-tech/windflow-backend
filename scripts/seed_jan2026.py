import asyncio
import logging
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

from app.services.data_loader import data_loader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    print("Starting full January 2026 Elexon BMRS fetch and cache...")
    await data_loader.fetch_and_cache_all()
    print(f"Complete! Loaded {len(data_loader.actuals)} actuals and {len(data_loader.forecasts)} forecasts.")

if __name__ == "__main__":
    asyncio.run(main())
