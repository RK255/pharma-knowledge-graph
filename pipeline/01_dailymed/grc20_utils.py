# grc20_utils.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "00_schema"))
from pharma_schema import PharmaSchema, generate_grc20_id

# Initialize schema
_schema = PharmaSchema()

# GRC-20 value types
GRC20_VALUE_TYPES = {
    "TEXT": 1,
    "NUMBER": 2, 
    "CHECKBOX": 3,
    "URL": 4,
    "TIME": 5,
    "POINT": 6
}

def get_attribute_id(name: str) -> str:
    """Get GRC-20 ID for an attribute from schema."""
    return _schema.attr(name)

def get_type_id(name: str) -> str:
    """Get GRC-20 ID for an entity type from schema."""
    return _schema.type_id(name)

def get_relation_id(name: str) -> str:
    """Get GRC-20 ID for a relation from schema."""
    return _schema.relations.get(name)

# Convenience dicts for backwards compatibility
ATTRIBUTES = {
    "name": _schema.attr("name"),
    "type": _schema.attr("type"),
    "description": _schema.attr("description"),
    "section_type": _schema.attr("section_type"),
    "content": _schema.attr("content"),
    "fda_set_id": _schema.attr("fda_set_id"),
    "effective_time": _schema.attr("effective_time"),
    "set_id": _schema.attr("set_id"),
}

ENTITY_TYPES = {
    "PackageInsert": _schema.type_id("PackageInsert"),
    "Section": _schema.type_id("Section"),
    "Manufacturer": _schema.type_id("Manufacturer"),
    "Provenance": _schema.type_id("Provenance"),
}

RELATIONS = {
    "has_section": _schema.relations.get("has_section"),
    "section_of": _schema.relations.get("section_of"),
    "manufactured_by": _schema.relations.get("manufactured_by"),
    "manufactures": _schema.relations.get("manufactures"),
}
