import json
from datetime import datetime
import os

class Config:
    # Network RPC URLs (add your own)
    RPC_URLS = {
        "ethereum": {
            "mainnet": "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY",
            "goerli": "https://eth-goerli.g.alchemy.com/v2/YOUR_KEY",
            "sepolia": "https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY"
        },
        "polygon": {
            "mainnet": "https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY",
            "mumbai": "https://polygon-mumbai.g.alchemy.com/v2/YOUR_KEY"
        },
        "arbitrum": {
            "mainnet": "https://arb-mainnet.g.alchemy.com/v2/YOUR_KEY",
            "goerli": "https://arb-goerli.g.alchemy.com/v2/YOUR_KEY",
            "sepolia": "https://arb-sepolia.g.alchemy.com/v2/YOUR_KEY"
        },
        "optimism": {
            "mainnet": "https://opt-mainnet.g.alchemy.com/v2/YOUR_KEY",
            "goerli": "https://opt-goerli.g.alchemy.com/v2/YOUR_KEY"
        },
        "base": {
            "mainnet": "https://base-mainnet.g.alchemy.com/v2/YOUR_KEY",
            "goerli": "https://base-goerli.g.alchemy.com/v2/YOUR_KEY"
        }
    }
    
    # Common contract ABIs
    COMMON_ABIS = {
        "erc721_mint": [
            {
                "inputs": [],
                "name": "mint",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "publicMint",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "mintPublic",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "quantity", "type": "uint256"}],
                "name": "mint",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            }
        ],
        "erc1155_mint": [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "id", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"}
                ],
                "name": "mint",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            }
        ]
    }
    
    # Default bot settings
    DEFAULT_SETTINGS = {
        "max_gas_price_gwei": 100,
        "max_priority_fee_gwei": 2,
        "retry_count": 50,
        "retry_delay": 0.5,
        "check_interval": 1.0,
        "gas_multiplier": 1.2,
        "timeout": 30
    }
    
    @staticmethod
    def get_rpc_url(network: str, chain: str = "mainnet") -> str:
        """Get RPC URL for specific network and chain"""
        network = network.lower()
        chain = chain.lower()
        
        if network in Config.RPC_URLS and chain in Config.RPC_URLS[network]:
            return Config.RPC_URLS[network][chain]
        
        # Fallback to environment variable
        env_key = f"RPC_URL_{network.upper()}"
        return os.getenv(env_key, "")
    
    @staticmethod
    def save_wallet_info(wallet_name: str, address: str, private_key_encrypted: str):
        """Save wallet info to encrypted file"""
        # Create wallets directory if it doesn't exist
        os.makedirs("wallets", exist_ok=True)
        
        wallet_data = {
            "name": wallet_name,
            "address": address,
            "private_key_encrypted": private_key_encrypted,
            "created_at": datetime.now().isoformat(),
            "last_used": None,
            "mint_count": 0,
            "success_rate": 0.0
        }
        
        file_path = f"wallets/{wallet_name}.json"
        with open(file_path, "w") as f:
            json.dump(wallet_data, f, indent=2)
        
        print(f"✅ Wallet '{wallet_name}' saved to {file_path}")
        return file_path
    
    @staticmethod
    def load_wallet_info(wallet_name: str) -> dict:
        """Load wallet info from file"""
        file_path = f"wallets/{wallet_name}.json"
        
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Wallet file '{file_path}' not found")
            return {}
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in wallet file '{file_path}'")
            return {}
    
    @staticmethod
    def update_wallet_stats(wallet_name: str, success: bool = True):
        """Update wallet statistics after mint attempt"""
        wallet_data = Config.load_wallet_info(wallet_name)
        
        if wallet_data:
            wallet_data["last_used"] = datetime.now().isoformat()
            
            if success:
                wallet_data["mint_count"] = wallet_data.get("mint_count", 0) + 1
            
            # Calculate success rate (simplified)
            total_attempts = wallet_data.get("total_attempts", 0) + 1
            successful_mints = wallet_data.get("mint_count", 0)
            wallet_data["total_attempts"] = total_attempts
            wallet_data["success_rate"] = (successful_mints / total_attempts * 100) if total_attempts > 0 else 0
            
            Config.save_wallet_info(wallet_name, 
                                  wallet_data["address"], 
                                  wallet_data["private_key_encrypted"])
    
    @staticmethod
    def get_contract_abi(contract_type: str = "erc721_mint") -> list:
        """Get ABI for specific contract type"""
        return Config.COMMON_ABIS.get(contract_type, Config.COMMON_ABIS["erc721_mint"])
    
    @staticmethod
    def save_transaction_log(tx_hash: str, network: str, status: str, 
                           gas_used: int, gas_price: float, value: float):
        """Save transaction log to file"""
        log_entry = {
            "tx_hash": tx_hash,
            "network": network,
            "status": status,
            "gas_used": gas_used,
            "gas_price_gwei": gas_price,
            "value_eth": value,
            "timestamp": datetime.now().isoformat(),
            "block_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Create logs directory if it doesn't exist
        os.makedirs("logs", exist_ok=True)
        
        log_file = f"logs/transactions_{datetime.now().strftime('%Y%m%d')}.json"
        
        # Load existing logs or create new list
        try:
            with open(log_file, "r") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []
        
        # Add new log entry
        logs.append(log_entry)
        
        # Save updated logs
        with open(log_file, "w") as f:
            json.dump(logs, f, indent=2)
        
        return log_file
    
    @staticmethod
    def load_settings() -> dict:
        """Load settings from JSON file"""
        settings_file = "settings.json"
        
        try:
            with open(settings_file, "r") as f:
                user_settings = json.load(f)
                
                # Merge with default settings
                settings = Config.DEFAULT_SETTINGS.copy()
                settings.update(user_settings)
                return settings
                
        except FileNotFoundError:
            print(f"⚠️  Settings file not found, using defaults")
            return Config.DEFAULT_SETTINGS.copy()
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in settings file")
            return Config.DEFAULT_SETTINGS.copy()
    
    @staticmethod
    def save_settings(settings: dict):
        """Save settings to JSON file"""
        settings_file = "settings.json"
        
        with open(settings_file, "w") as f:
            json.dump(settings, f, indent=2)
        
        print(f"✅ Settings saved to {settings_file}")