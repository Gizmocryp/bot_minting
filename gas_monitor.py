import asyncio
import aiohttp
from datetime import datetime
from colorama import Fore, Style

class GasMonitor:
    def __init__(self):
        self.ethgasstation_url = "https://api.etherscan.io/api?module=gastracker&action=gasoracle"
    
    async def get_gas_prices(self):
        """Get current gas prices from various sources"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.ethgasstation_url) as response:
                    data = await response.json()
                    
                    if data['status'] == '1':
                        result = data['result']
                        print(Fore.CYAN + f"⛽ Current Gas Prices:")
                        print(Fore.GREEN + f"   Low: {result['SafeGasPrice']} Gwei")
                        print(Fore.YELLOW + f"   Medium: {result['ProposeGasPrice']} Gwei")
                        print(Fore.RED + f"   High: {result['FastGasPrice']} Gwei")
                        print(Fore.BLUE + f"   Base Fee: {result.get('suggestBaseFee', 'N/A')} Gwei")
        except Exception as e:
            print(Fore.RED + f"Error fetching gas prices: {e}")

async def monitor_gas(interval=30):
    """Monitor gas prices periodically"""
    monitor = GasMonitor()
    while True:
        current_time = datetime.now().strftime("%H:%M:%S")
        print(Fore.MAGENTA + f"\n[{current_time}] Gas Update:")
        await monitor.get_gas_prices()
        await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(monitor_gas())