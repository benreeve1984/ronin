# Secrets Management for Ronin
# =============================
# Secure storage and retrieval of API keys and other secrets.
# Stores secrets globally in ~/.ronin/secrets for use across all projects.

import os
import json
import stat
from pathlib import Path
from typing import Optional, Dict, List
import hashlib
import base64
import getpass
from logging_config import get_logger

# Try to import keyring for OS keychain support
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Try to import cryptography for encryption
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = get_logger("secrets_manager")

# Global config directory
CONFIG_DIR = Path.home() / ".ronin"
SECRETS_FILE = CONFIG_DIR / "secrets.json"
ENCRYPTED_SECRETS_FILE = CONFIG_DIR / "secrets.enc"

# Keyring service name
KEYRING_SERVICE = "ronin-agent"

class SecretsManager:
    """
    Manages API keys and secrets for Ronin.
    
    Storage hierarchy:
    1. OS Keychain (if available) - Most secure
    2. Encrypted file - Good security
    3. Protected JSON file - Basic security
    
    Secrets are stored globally in ~/.ronin/ and available
    to all Ronin sessions regardless of current directory.
    """
    
    def __init__(self, use_keyring: bool = True):
        """
        Initialize the secrets manager.
        
        Args:
            use_keyring: Whether to try using OS keychain
        """
        self.use_keyring = use_keyring and KEYRING_AVAILABLE
        self._ensure_config_dir()
        self._encryption_key = None
        
        logger.info("Secrets manager initialized", 
                   extra={"context": {"keyring_available": KEYRING_AVAILABLE,
                                     "use_keyring": self.use_keyring}})
    
    def _ensure_config_dir(self):
        """Ensure the config directory exists with proper permissions."""
        CONFIG_DIR.mkdir(exist_ok=True)
        # Set restrictive permissions (owner only)
        try:
            os.chmod(CONFIG_DIR, stat.S_IRWXU)  # 700
        except:
            pass  # Windows doesn't support chmod
    
    def _get_encryption_key(self) -> bytes:
        """
        Get or create an encryption key for file-based storage.
        
        Uses a machine-specific key derived from username and hostname.
        Not perfect security, but better than plaintext.
        """
        if self._encryption_key:
            return self._encryption_key
        
        if not CRYPTO_AVAILABLE:
            # Simple obfuscation when cryptography not available
            import socket
            machine_id = f"{getpass.getuser()}@{socket.gethostname()}"
            self._encryption_key = hashlib.sha256(machine_id.encode()).digest()
            return self._encryption_key
        
        # Derive key from machine-specific data
        import socket
        machine_id = f"{getpass.getuser()}@{socket.gethostname()}".encode()
        
        # Use PBKDF2 to derive a key
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'ronin-static-salt',  # Static salt for reproducibility
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(machine_id))
        self._encryption_key = key
        return key
    
    def _obfuscate(self, data: str) -> bytes:
        """Simple obfuscation when cryptography not available."""
        key = self._get_encryption_key()
        # XOR with key bytes (not secure, but better than plaintext)
        obfuscated = []
        for i, char in enumerate(data.encode()):
            obfuscated.append(char ^ key[i % len(key)])
        return base64.b64encode(bytes(obfuscated))
    
    def _deobfuscate(self, data: bytes) -> str:
        """Reverse obfuscation."""
        key = self._get_encryption_key()
        decoded = base64.b64decode(data)
        deobfuscated = []
        for i, byte in enumerate(decoded):
            deobfuscated.append(byte ^ key[i % len(key)])
        return bytes(deobfuscated).decode()
    
    def set_secret(self, provider: str, key: str, value: str) -> bool:
        """
        Store a secret for a provider.
        
        Args:
            provider: Provider name (e.g., "anthropic", "openai")
            key: Key name (e.g., "api_key", "org_id")
            value: Secret value
            
        Returns:
            True if successful
        """
        secret_id = f"{provider}_{key}"
        
        # Try OS keychain first
        if self.use_keyring:
            try:
                keyring.set_password(KEYRING_SERVICE, secret_id, value)
                logger.info(f"Secret stored in keychain: {secret_id}")
                return True
            except Exception as e:
                logger.warning(f"Keychain storage failed: {e}, falling back to file")
        
        # Fall back to encrypted/obfuscated file
        return self._store_in_file(provider, key, value, encrypted=True)
    
    def get_secret(self, provider: str, key: str) -> Optional[str]:
        """
        Retrieve a secret for a provider.
        
        Args:
            provider: Provider name
            key: Key name
            
        Returns:
            Secret value or None if not found
        """
        secret_id = f"{provider}_{key}"
        
        # Try OS keychain first
        if self.use_keyring:
            try:
                value = keyring.get_password(KEYRING_SERVICE, secret_id)
                if value:
                    logger.debug(f"Secret retrieved from keychain: {secret_id}")
                    return value
            except Exception as e:
                logger.debug(f"Keychain retrieval failed: {e}")
        
        # Try encrypted file
        if ENCRYPTED_SECRETS_FILE.exists():
            try:
                return self._read_from_file(provider, key, encrypted=True)
            except Exception as e:
                logger.debug(f"Encrypted file read failed: {e}")
        
        # Try plain JSON file
        if SECRETS_FILE.exists():
            return self._read_from_file(provider, key, encrypted=False)
        
        return None
    
    def _store_in_file(self, provider: str, key: str, value: str, 
                      encrypted: bool = True) -> bool:
        """Store secret in file (encrypted or plain)."""
        file_path = ENCRYPTED_SECRETS_FILE if encrypted else SECRETS_FILE
        
        # Read existing secrets
        secrets = {}
        if file_path.exists():
            if encrypted:
                try:
                    if CRYPTO_AVAILABLE:
                        cipher = Fernet(self._get_encryption_key())
                        encrypted_data = file_path.read_bytes()
                        decrypted_data = cipher.decrypt(encrypted_data)
                        secrets = json.loads(decrypted_data)
                    else:
                        # Use simple obfuscation
                        obfuscated_data = file_path.read_bytes()
                        decrypted_data = self._deobfuscate(obfuscated_data)
                        secrets = json.loads(decrypted_data)
                except:
                    secrets = {}
            else:
                try:
                    secrets = json.loads(file_path.read_text())
                except:
                    secrets = {}
        
        # Update secrets
        if provider not in secrets:
            secrets[provider] = {}
        secrets[provider][key] = value
        
        # Write back
        if encrypted:
            if CRYPTO_AVAILABLE:
                cipher = Fernet(self._get_encryption_key())
                encrypted_data = cipher.encrypt(json.dumps(secrets).encode())
                file_path.write_bytes(encrypted_data)
            else:
                # Use simple obfuscation
                obfuscated_data = self._obfuscate(json.dumps(secrets))
                file_path.write_bytes(obfuscated_data)
        else:
            file_path.write_text(json.dumps(secrets, indent=2))
        
        # Set restrictive permissions
        try:
            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
        except:
            pass
        
        method = "encrypted" if CRYPTO_AVAILABLE and encrypted else "obfuscated" if encrypted else "protected"
        logger.info(f"Secret stored in {method} file: {provider}_{key}")
        return True
    
    def _read_from_file(self, provider: str, key: str, 
                       encrypted: bool = True) -> Optional[str]:
        """Read secret from file (encrypted or plain)."""
        file_path = ENCRYPTED_SECRETS_FILE if encrypted else SECRETS_FILE
        
        if not file_path.exists():
            return None
        
        try:
            if encrypted:
                if CRYPTO_AVAILABLE:
                    cipher = Fernet(self._get_encryption_key())
                    encrypted_data = file_path.read_bytes()
                    decrypted_data = cipher.decrypt(encrypted_data)
                    secrets = json.loads(decrypted_data)
                else:
                    # Use simple obfuscation
                    obfuscated_data = file_path.read_bytes()
                    decrypted_data = self._deobfuscate(obfuscated_data)
                    secrets = json.loads(decrypted_data)
            else:
                secrets = json.loads(file_path.read_text())
            
            return secrets.get(provider, {}).get(key)
        except Exception as e:
            logger.error(f"Failed to read secret from file: {e}")
            return None
    
    def remove_secret(self, provider: str, key: str) -> bool:
        """
        Remove a secret.
        
        Args:
            provider: Provider name
            key: Key name
            
        Returns:
            True if removed
        """
        secret_id = f"{provider}_{key}"
        removed = False
        
        # Remove from keychain
        if self.use_keyring:
            try:
                keyring.delete_password(KEYRING_SERVICE, secret_id)
                removed = True
                logger.info(f"Secret removed from keychain: {secret_id}")
            except:
                pass
        
        # Remove from files
        for encrypted in [True, False]:
            file_path = ENCRYPTED_SECRETS_FILE if encrypted else SECRETS_FILE
            if file_path.exists():
                try:
                    if encrypted:
                        if CRYPTO_AVAILABLE:
                            cipher = Fernet(self._get_encryption_key())
                            encrypted_data = file_path.read_bytes()
                            decrypted_data = cipher.decrypt(encrypted_data)
                            secrets = json.loads(decrypted_data)
                        else:
                            # Use simple obfuscation
                            obfuscated_data = file_path.read_bytes()
                            decrypted_data = self._deobfuscate(obfuscated_data)
                            secrets = json.loads(decrypted_data)
                    else:
                        secrets = json.loads(file_path.read_text())
                    
                    if provider in secrets and key in secrets[provider]:
                        del secrets[provider][key]
                        if not secrets[provider]:
                            del secrets[provider]
                        
                        # Write back
                        if encrypted:
                            encrypted_data = cipher.encrypt(json.dumps(secrets).encode())
                            file_path.write_bytes(encrypted_data)
                        else:
                            file_path.write_text(json.dumps(secrets, indent=2))
                        
                        removed = True
                        logger.info(f"Secret removed from file: {secret_id}")
                except:
                    pass
        
        return removed
    
    def list_secrets(self) -> Dict[str, List[str]]:
        """
        List all stored secrets (keys only, not values).
        
        Returns:
            Dictionary of provider -> list of keys
        """
        all_secrets = {}
        
        # Check keychain
        if self.use_keyring:
            try:
                # This is platform-specific, might not work everywhere
                import keyring.backends
                # We'd need to enumerate, but keyring doesn't provide this easily
                # Skip for now
                pass
            except:
                pass
        
        # Check files
        for encrypted in [True, False]:
            file_path = ENCRYPTED_SECRETS_FILE if encrypted else SECRETS_FILE
            if file_path.exists():
                try:
                    if encrypted:
                        if CRYPTO_AVAILABLE:
                            cipher = Fernet(self._get_encryption_key())
                            encrypted_data = file_path.read_bytes()
                            decrypted_data = cipher.decrypt(encrypted_data)
                            secrets = json.loads(decrypted_data)
                        else:
                            # Use simple obfuscation
                            obfuscated_data = file_path.read_bytes()
                            decrypted_data = self._deobfuscate(obfuscated_data)
                            secrets = json.loads(decrypted_data)
                    else:
                        secrets = json.loads(file_path.read_text())
                    
                    for provider, keys in secrets.items():
                        if provider not in all_secrets:
                            all_secrets[provider] = []
                        all_secrets[provider].extend(keys.keys())
                except:
                    pass
        
        # Deduplicate
        for provider in all_secrets:
            all_secrets[provider] = list(set(all_secrets[provider]))
        
        return all_secrets

# Convenience functions
_manager = None

def get_manager() -> SecretsManager:
    """Get the global secrets manager instance."""
    global _manager
    if _manager is None:
        _manager = SecretsManager()
    return _manager

def get_api_key(provider: str = "anthropic") -> Optional[str]:
    """
    Get API key for a provider.
    
    Checks in order:
    1. Environment variable (e.g., ANTHROPIC_API_KEY)
    2. Stored secret
    
    Args:
        provider: Provider name
        
    Returns:
        API key or None
    """
    # Check environment variable first
    env_var = f"{provider.upper()}_API_KEY"
    if env_value := os.getenv(env_var):
        logger.debug(f"Using API key from environment: {env_var}")
        return env_value
    
    # Check stored secrets
    manager = get_manager()
    if stored_value := manager.get_secret(provider, "api_key"):
        logger.debug(f"Using API key from secrets: {provider}")
        return stored_value
    
    logger.warning(f"No API key found for {provider}")
    return None

def set_api_key(provider: str, api_key: str) -> bool:
    """
    Store API key for a provider.
    
    Args:
        provider: Provider name
        api_key: API key value
        
    Returns:
        True if successful
    """
    manager = get_manager()
    return manager.set_secret(provider, "api_key", api_key)

def remove_api_key(provider: str) -> bool:
    """
    Remove stored API key for a provider.
    
    Args:
        provider: Provider name
        
    Returns:
        True if removed
    """
    manager = get_manager()
    return manager.remove_secret(provider, "api_key")

def list_providers() -> List[str]:
    """
    List providers with stored API keys.
    
    Returns:
        List of provider names
    """
    manager = get_manager()
    secrets = manager.list_secrets()
    providers = []
    for provider, keys in secrets.items():
        if "api_key" in keys:
            providers.append(provider)
    return providers