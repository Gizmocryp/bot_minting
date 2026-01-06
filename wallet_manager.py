import os
import json
from datetime import datetime
from colorama import Fore, Style
from cryptography.fernet import Fernet
import base64

class WalletManager:
    def __init__(self, encryption_key=None):
        """
        Initialize Wallet Manager
        
        Args:
            encryption_key: Key for encrypting private keys. 
                           If None, will try to load from .env or generate new.
        """
        self.encryption_key = encryption_key or self.load_or_generate_key()
        self.cipher = Fernet(self.encryption_key)
        self.wallets_dir = "wallets"
        os.makedirs(self.wallets_dir, exist_ok=True)
    
    @staticmethod
    def load_or_generate_key():
        """Load encryption key from .env or generate new"""
        from dotenv import load_dotenv
        load_dotenv()
        
        key = os.getenv("ENCRYPTION_KEY")
        
        if key:
            # Decode from base64
            return base64.urlsafe_b64decode(key.encode())
        else:
            # Generate new key
            new_key = Fernet.generate_key()
            
            # Save to .env
            with open(".env", "a") as f:
                f.write(f"\nENCRYPTION_KEY={base64.urlsafe_b64encode(new_key).decode()}")
            
            print(Fore.YELLOW + "🔑 Generated new encryption key and saved to .env")
            return new_key
    
    def encrypt_private_key(self, private_key: str) -> str:
        """Encrypt private key"""
        encrypted = self.cipher.encrypt(private_key.encode())
        return encrypted.decode()
    
    def decrypt_private_key(self, encrypted_key: str) -> str:
        """Decrypt private key"""
        decrypted = self.cipher.decrypt(encrypted_key.encode())
        return decrypted.decode()
    
    def add_wallet(self, wallet_name: str, private_key: str, public_key: str = None):
        """Add a new wallet to manager"""
        from web3 import Web3
        
        # Validate private key
        try:
            account = Web3().eth.account.from_key(private_key)
            if public_key and public_key.lower() != account.address.lower():
                print(Fore.RED + "❌ Public key doesn't match private key")
                return False
            
            public_key = account.address
        except Exception as e:
            print(Fore.RED + f"❌ Invalid private key: {e}")
            return False
        
        # Encrypt private key
        encrypted_key = self.encrypt_private_key(private_key)
        
        # Create wallet data
        wallet_data = {
            "name": wallet_name,
            "address": public_key,
            "private_key_encrypted": encrypted_key,
            "created_at": datetime.now().isoformat(),
            "last_used": None,
            "total_mints": 0,
            "successful_mints": 0,
            "failed_mints": 0,
            "total_gas_spent": 0,
            "tags": []
        }
        
        # Save to file
        wallet_file = os.path.join(self.wallets_dir, f"{wallet_name}.json")
        with open(wallet_file, "w") as f:
            json.dump(wallet_data, f, indent=2)
        
        print(Fore.GREEN + f"✅ Wallet '{wallet_name}' added successfully")
        print(Fore.CYAN + f"   Address: {public_key}")
        return True
    
    def get_wallet(self, wallet_name: str) -> dict:
        """Get wallet data by name"""
        wallet_file = os.path.join(self.wallets_dir, f"{wallet_name}.json")
        
        try:
            with open(wallet_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print(Fore.RED + f"❌ Wallet '{wallet_name}' not found")
            return None
    
    def get_all_wallets(self) -> list:
        """Get all wallets"""
        wallets = []
        
        for filename in os.listdir(self.wallets_dir):
            if filename.endswith(".json"):
                wallet_name = filename[:-5]
                wallet = self.get_wallet(wallet_name)
                if wallet:
                    wallets.append(wallet)
        
        return wallets
    
    def get_wallet_private_key(self, wallet_name: str) -> str:
        """Get decrypted private key for wallet"""
        wallet = self.get_wallet(wallet_name)
        
        if wallet and "private_key_encrypted" in wallet:
            try:
                return self.decrypt_private_key(wallet["private_key_encrypted"])
            except Exception as e:
                print(Fore.RED + f"❌ Failed to decrypt private key: {e}")
                return None
        
        return None
    
    def update_wallet_stats(self, wallet_name: str, success: bool, gas_spent: float = 0):
        """Update wallet statistics"""
        wallet = self.get_wallet(wallet_name)
        
        if wallet:
            wallet["last_used"] = datetime.now().isoformat()
            
            if success:
                wallet["successful_mints"] = wallet.get("successful_mints", 0) + 1
            else:
                wallet["failed_mints"] = wallet.get("failed_mints", 0) + 1
            
            wallet["total_mints"] = wallet.get("total_mints", 0) + 1
            wallet["total_gas_spent"] = wallet.get("total_gas_spent", 0) + gas_spent
            
            # Calculate success rate
            if wallet["total_mints"] > 0:
                wallet["success_rate"] = (wallet["successful_mints"] / wallet["total_mints"]) * 100
            
            # Save updated wallet
            wallet_file = os.path.join(self.wallets_dir, f"{wallet_name}.json")
            with open(wallet_file, "w") as f:
                json.dump(wallet, f, indent=2)
            
            return True
        
        return False
    
    def remove_wallet(self, wallet_name: str) -> bool:
        """Remove wallet from manager"""
        wallet_file = os.path.join(self.wallets_dir, f"{wallet_name}.json")
        
        if os.path.exists(wallet_file):
            os.remove(wallet_file)
            print(Fore.GREEN + f"✅ Wallet '{wallet_name}' removed")
            return True
        else:
            print(Fore.RED + f"❌ Wallet '{wallet_name}' not found")
            return False
    
    def list_wallets(self) -> None:
        """List all wallets with statistics"""
        wallets = self.get_all_wallets()
        
        if not wallets:
            print(Fore.YELLOW + "📭 No wallets found")
            return
        
        print(Fore.CYAN + "📋 WALLET LIST")
        print(Fore.CYAN + "=" * 80)
        
        for i, wallet in enumerate(wallets, 1):
            success_rate = wallet.get("success_rate", 0)
            status_color = Fore.GREEN if success_rate > 70 else Fore.YELLOW if success_rate > 30 else Fore.RED
            
            print(f"{i}. {Fore.BLUE}{wallet['name']}{Style.RESET_ALL}")
            print(f"   Address: {wallet['address'][:10]}...{wallet['address'][-8:]}")
            print(f"   Created: {wallet['created_at'][:10]}")
            print(f"   Mints: {wallet.get('successful_mints', 0)}/{wallet.get('total_mints', 0)} successful")
            print(f"   Success Rate: {status_color}{success_rate:.1f}%{Style.RESET_ALL}")
            print(f"   Total Gas: {wallet.get('total_gas_spent', 0):.4f} ETH")
            
            if wallet.get('tags'):
                print(f"   Tags: {', '.join(wallet['tags'])}")
            
            print()