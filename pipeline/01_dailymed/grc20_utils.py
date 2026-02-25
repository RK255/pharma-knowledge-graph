# grc20_utils.py
import uuid
import base58

# GRC-20 value types
GRC20_VALUE_TYPES = {
    "TEXT": 1,
    "NUMBER": 2, 
    "CHECKBOX": 3,
    "URL": 4,
    "TIME": 5,
    "POINT": 6
}

def generate_grc20_id():
    """Generate a valid GRC-20 entity ID (22-character Base58)"""
    # Create a UUID4 and take only first 16 bytes
    uuid_bytes = uuid.uuid4().bytes[:16]
    # Convert to Base58
    return base58.b58encode(uuid_bytes).decode()

# Human-readable attribute mappings
ATTRIBUTES = {
    "name": "LuBWqZAu6pz54eiJS5mLv8",
    "type": "Jfmby78N4BCseZinBmdVov", 
    "description": "LA1DqP5v6QAdsgLPXGF3YA",
    "section_type": "7YHk6qYkNDaAtNb8GwmysF",
    "provenance_hash": "WQfdWjboZWFuTseDhG5Cw1",
    "has_section": "QYbjCM6NT9xmh2hFGsqpQX"
}

# Entity type mappings
ENTITY_TYPES = {
    "drug": "Jfmby78N4BCseZinBmdVov",
    "section": "QYbjCM6NT9xmh2hFGsqpQX",
    "manufacturer": "GscJ2GELQjmLoaVrYyR3xm"
}
