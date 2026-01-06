import os
import json
import time
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from colorama import init, Fore, Style
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.middleware import geth_poa_middleware
from wallet_manager import WalletManager

# Initialize colorama for colored output
init(autoreset=True)

load_dotenv()

class NFTMintingBot:
    def __init__(self, network="ethereum", wallet_name=None):
        """Initialize the NFT minting bot"""
        self.network = network.lower()
        self.setup_network_config()

        # Initialize wallet manager
        self.wallet_manager = WalletManager()
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if self.network in ['polygon', 'arbitrum']:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Load wallet
        self.private_key = os.getenv('PRIVATE_KEY')
        self.public_key = os.getenv('PUBLIC_KEY')
        
        if wallet_name:
            wallet_data = self.wallet_manager.get_wallet(wallet_name)
            if wallet_data:
                self.private_key = self.wallet_manager.get_wallet_private_key(wallet_name)
                self.public_key = wallet_data["address"]
                self.wallet_name = wallet_name
            else:
                raise ValueError(f"Wallet '{wallet_name}' not found")
        else:
            # Fallback to environment variables
            self.private_key = os.getenv('PRIVATE_KEY')
            self.public_key = os.getenv('PUBLIC_KEY')
            self.wallet_name = "default"
        
        # Load contract
        self.contract_address = os.getenv('CONTRACT_ADDRESS')
        mint_function_abi = os.getenv('MINT_FUNCTION_ABI')
        
        if not self.contract_address or not mint_function_abi:
            raise ValueError("Contract configuration not found")
        
        try:
            self.mint_abi = json.loads(mint_function_abi)
        except json.JSONDecodeError:
            raise ValueError("Invalid MINT_FUNCTION_ABI JSON format")
        
        # Contract setup
        self.contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.contract_address),
            abi=self.mint_abi
        )
        
        # Bot configuration
        self.mint_price = float(os.getenv('MINT_PRICE', '0.05'))
        self.max_gas_price = int(os.getenv('MAX_GAS_PRICE_GWEI', '100'))
        self.max_priority_fee = int(os.getenv('MAX_PRIORITY_FEE_GWEI', '2'))
        self.max_retries = int(os.getenv('RETRY_COUNT', '50'))
        self.retry_delay = float(os.getenv('RETRY_DELAY', '0.5'))
        self.check_interval = float(os.getenv('CHECK_INTERVAL', '1.0'))
        
        # State tracking
        self.mint_successful = False
        self.total_attempts = 0
        self.successful_mints = 0
        
        print(Fore.GREEN + f"✅ Bot initialized for {self.network}")
        print(Fore.CYAN + f"📝 Wallet: {self.public_key[:8]}...{self.public_key[-6:]}")
        print(Fore.CYAN + f"📄 Contract: {self.contract_address[:8]}...{self.contract_address[-6:]}")
    
    def setup_network_config(self):
        """Setup network-specific configuration"""
        network_rpc_map = {
            'ethereum': os.getenv('RPC_URL_ETH'),
            'polygon': os.getenv('RPC_URL_POLYGON'),
            'arbitrum': os.getenv('RPC_URL_ARBITRUM')
        }
        
        self.rpc_url = network_rpc_map.get(self.network)
        if not self.rpc_url:
            raise ValueError(f"RPC URL for {self.network} not found in environment variables")
    
    def get_current_gas_price(self) -> Dict[str, int]:
        """Get current gas prices from the network"""
        try:
            base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
            if base_fee:
                base_fee_gwei = self.w3.from_wei(base_fee, 'gwei')
                max_priority = min(self.max_priority_fee, base_fee_gwei * 0.1)
                max_fee = min(self.max_gas_price, base_fee_gwei + max_priority)
                
                return {
                    'maxFeePerGas': self.w3.to_wei(max_fee, 'gwei'),
                    'maxPriorityFeePerGas': self.w3.to_wei(max_priority, 'gwei')
                }
        except:
            pass
        
        # Fallback to legacy gas price
        gas_price = self.w3.eth.gas_price
        return {
            'gasPrice': min(gas_price, self.w3.to_wei(self.max_gas_price, 'gwei'))
        }
    
    async def check_mint_status(self) -> bool:
        """Check if mint is live"""
        try:
            # Example: Check mint status through contract function
            # Modify based on your contract's specific functions
            try:
                # Try public sale status
                is_public_mint_active = self.contract.functions.isPublicMintActive().call()
                return is_public_mint_active
            except:
                # Try different function names
                try:
                    is_mint_active = self.contract.functions.mintActive().call()
                    return is_mint_active
                except:
                    # If no specific function, assume mint is active
                    return True
        except Exception as e:
            print(Fore.YELLOW + f"⚠️  Error checking mint status: {e}")
            return False
    
    async def create_mint_transaction(self) -> Dict[str, Any]:
        """Create mint transaction"""
        nonce = self.w3.eth.get_transaction_count(self.public_key)
        gas_params = self.get_current_gas_price()
        
        # Prepare transaction
        mint_price_wei = self.w3.to_wei(self.mint_price, 'ether')
        
        transaction = {
            'from': self.public_key,
            'to': self.contract_address,
            'value': mint_price_wei,
            'nonce': nonce,
            'chainId': self.w3.eth.chain_id,
            **gas_params
        }
        
        # Estimate gas
        try:
            gas_estimate = self.w3.eth.estimate_gas(transaction)
            transaction['gas'] = int(gas_estimate * 1.2)  # 20% buffer
        except:
            transaction['gas'] = 200000  # Default gas limit
        
        # Encode mint function call
        try:
            # Try standard mint function
            mint_tx = self.contract.functions.mint().build_transaction(transaction)
            return mint_tx
        except:
            try:
                # Try publicMint function
                mint_tx = self.contract.functions.publicMint().build_transaction(transaction)
                return mint_tx
            except Exception as e:
                print(Fore.RED + f"❌ Error building transaction: {e}")
                return None
    
    async def send_transaction(self, signed_tx) -> Optional[str]:
        """Send transaction and return tx hash"""
        try:
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return tx_hash.hex()
        except Exception as e:
            print(Fore.RED + f"❌ Error sending transaction: {e}")
            return None
    
    async def wait_for_transaction(self, tx_hash: str) -> bool:
        """Wait for transaction confirmation"""
        attempts = 0
        max_attempts = 30
        
        while attempts < max_attempts:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    if receipt['status'] == 1:
                        print(Fore.GREEN + f"✅ Transaction successful! Hash: {tx_hash}")
                        return True
                    else:
                        print(Fore.RED + f"❌ Transaction failed! Hash: {tx_hash}")
                        return False
            except TransactionNotFound:
                pass
            
            attempts += 1
            await asyncio.sleep(2)
        
        print(Fore.YELLOW + f"⚠️  Transaction pending: {tx_hash}")
        return False
    
    async def attempt_mint(self) -> bool:
        """Attempt to mint one NFT"""
        try:
            print(Fore.CYAN + "🔄 Creating mint transaction...")
            
            # Check if mint is active
            if not await self.check_mint_status():
                print(Fore.YELLOW + "⏳ Mint is not active yet")
                return False
            
            # Create transaction
            transaction = await self.create_mint_transaction()
            if not transaction:
                return False
            
            # Sign transaction
            signed_tx = self.w3.eth.account.sign_transaction(transaction, self.private_key)
            
            # Send transaction
            tx_hash = await self.send_transaction(signed_tx)
            if not tx_hash:
                return False
            
            # Wait for confirmation
            success = await self.wait_for_transaction(tx_hash)
            
            if success:
                self.successful_mints += 1
                print(Fore.GREEN + f"🎉 Successfully minted NFT #{self.successful_mints}!")
                print(Fore.GREEN + f"📊 Total attempts: {self.total_attempts}")
            
            return success
            
        except Exception as e:
            print(Fore.RED + f"❌ Error in mint attempt: {e}")
            return False
    
    async def run_continuous_mint(self, target_count: int = 1):
        """Run continuous minting until target count is reached"""
        print(Fore.GREEN + f"🚀 Starting continuous minting. Target: {target_count} NFT(s)")
        
        while self.successful_mints < target_count:
            self.total_attempts += 1
            
            print(Fore.MAGENTA + f"\n📈 Attempt #{self.total_attempts}")
            print(Fore.MAGENTA + f"✅ Successful mints: {self.successful_mints}/{target_count}")
            
            success = await self.attempt_mint()
            
            if success and self.successful_mints >= target_count:
                print(Fore.GREEN + "🎯 Target reached! Stopping bot.")
                break
            
            if not success:
                print(Fore.YELLOW + f"⏳ Retrying in {self.retry_delay} seconds...")
                await asyncio.sleep(self.retry_delay)
    
    async def monitor_and_mint(self):
        """Monitor for mint start and then begin minting"""
        print(Fore.CYAN + "👀 Monitoring for mint start...")
        
        while True:
            if await self.check_mint_status():
                print(Fore.GREEN + "🔥 Mint is LIVE! Starting minting process...")
                await self.run_continuous_mint(target_count=1)
                break
            else:
                current_time = datetime.now().strftime("%H:%M:%S")
                print(Fore.YELLOW + f"[{current_time}] Mint not active yet. Checking again in {self.check_interval} seconds...")
                await asyncio.sleep(self.check_interval)

def main():
    """Main function"""
    print(Fore.BLUE + "=" * 50)
    print(Fore.BLUE + "🤖 NFT MINTING BOT")
    print(Fore.BLUE + "=" * 50)
    
    try:
        # Get user input
        network = input("Enter network (ethereum/polygon/arbitrum) [ethereum]: ").strip() or "ethereum"
        mode = input("Enter mode (monitor/immediate) [monitor]: ").strip() or "monitor"
        
        if mode == "immediate":
            target_count = int(input("Enter number of NFTs to mint [1]: ").strip() or "1")
        
        # Initialize bot
        bot = NFTMintingBot(network=network)
        
        # Run bot
        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n👋 Bot stopped by user")
    except Exception as e:
        print(Fore.RED + f"💥 Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()