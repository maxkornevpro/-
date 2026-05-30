"""
Token encryption/decryption for subscription URLs
Uses simple encryption with secret key
"""

import base64
import hashlib
from config import BOT_TOKEN

# Generate secret key from bot token
SECRET_KEY = hashlib.sha256(BOT_TOKEN.encode()).digest()

def encrypt_user_id(user_id: int) -> str:
    """Encrypt user ID to token."""
    # Convert to bytes
    user_bytes = str(user_id).encode()
    
    # Simple XOR with key (for URL-safe tokens)
    encrypted = bytes([b ^ SECRET_KEY[i % len(SECRET_KEY)] for i, b in enumerate(user_bytes)])
    
    # Base64 encode for URL safety
    token = base64.urlsafe_b64encode(encrypted).decode().rstrip('=')
    return token

def decrypt_token(token: str) -> int:
    """Decrypt token back to user ID."""
    try:
        # Add padding if needed
        padding = 4 - len(token) % 4
        if padding != 4:
            token += '=' * padding
        
        # Base64 decode
        encrypted = base64.urlsafe_b64decode(token.encode())
        
        # XOR decrypt
        user_bytes = bytes([b ^ SECRET_KEY[i % len(SECRET_KEY)] for i, b in enumerate(encrypted)])
        
        return int(user_bytes.decode())
    except:
        return None

def generate_referral_link(user_id: int, bot_username: str = "AeroProjectVPN_bot") -> str:
    """Generate referral link for user."""
    token = encrypt_user_id(user_id)
    return f"https://t.me/{bot_username}?start=ref_{token}"
