#!/usr/bin/env python3
"""
Pharma Knowledge Graph Schema
=============================

GRC-20 compliant schema for pharmaceutical knowledge graph.

This module defines ALL entity types, attributes, and relation types
for the pharma knowledge graph using GRC-20 standard IDs.

GRC-20 Spec IDs (DO NOT CHANGE):
- Text:         LckSTmjBrYAJaFcDs89am5
- Number:       LBdMpTNyycNffsF51t2eSp
- Checkbox:     G9NpD4c7GB7nH5YU9Tesgf
- URL:          5xroh3gbWYbWY4oR3nFXzy
- Time:         3mswMrL91GuYTfBq29EuNE
- Point:        UZBZNbA7Uhx1f8ebLi1Qj5
- Type:         Jfmby78N4BCseZinBmdVov
- Attribute:    GscJ2GELQjmLoaVrYyR3xm
- Relation:     QtC4Ay8HNLwSd1kSARgcDE
- RelationType: 3WxYoAVreE4qFhkDUs5J3q
- From entity:  RERshk4JoYoMC17r1qAo9J
- To entity:    Qx8dASiTNsxxP3rJbd4Lzd
- Index:        WNopXUYxsSsE51gkJGWghe
- Name:         LuBWqZAu6pz54eiJS5mLv8
- Types:        Jfmby78N4BCseZinBmdVov
- Description:  LA1DqP5v6QAdsgLPXGF3YA

Usage:
    from pharma_schema import PharmaSchema
    
    schema = PharmaSchema()
    
    # Get attribute ID
    attr_id = schema.attr("name")
    
    # Get relation type ID
    rel_id = schema.rel("has_ingredient")
    
    # Create a triple
    triple = schema.triple(entity_id, "name", "Aspirin")
    
    # Create a relation
    relation_triples = schema.relation(from_id, "has_ingredient", to_id)
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid

# =============================================================================
# GRC-20 STANDARD IDS (from spec)
# =============================================================================

GRC20_NATIVE_TYPES = {
    "Text": "LckSTmjBrYAJaFcDs89am5",
    "Number": "LBdMpTNyycNffsF51t2eSp",
    "Checkbox": "G9NpD4c7GB7nH5YU9Tesgf",
    "URL": "5xroh3gbWYbWY4oR3nFXzy",
    "Time": "3mswMrL91GuYTfBq29EuNE",
    "Point": "UZBZNbA7Uhx1f8ebLi1Qj5",
}

GRC20_SYSTEM_TYPES = {
    "Type": "Jfmby78N4BCseZinBmdVov",
    "Attribute": "GscJ2GELQjmLoaVrYyR3xm",
    "Relation": "QtC4Ay8HNLwSd1kSARgcDE",
    "RelationType": "3WxYoAVreE4qFhkDUs5J3q",
}

GRC20_RELATION_ATTRIBUTES = {
    "from_entity": "RERshk4JoYoMC17r1qAo9J",
    "to_entity": "Qx8dASiTNsxxP3rJbd4Lzd",
    "index": "WNopXUYxsSsE51gkJGWghe",
}

GRC20_IMPLICIT_ATTRIBUTES = {
    "name": "LuBWqZAu6pz54eiJS5mLv8",
    "types": "Jfmby78N4BCseZinBmdVov",  # Same as Type
    "description": "LA1DqP5v6QAdsgLPXGF3YA",
}


def generate_grc20_id(seed: str = None) -> str:
    """
    Generate a valid GRC-20 ID (22 character Base58).
    
    If seed is provided, generates deterministically.
    Otherwise, generates randomly.
    """
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    
    if seed:
        # Deterministic ID from seed
        hash_bytes = hashlib.md5(seed.encode()).digest()
        uuid_bytes = uuid.UUID(bytes=hash_bytes).bytes
    else:
        # Random ID
        uuid_bytes = uuid.uuid4().bytes
    
    # Convert to number
    num = int.from_bytes(uuid_bytes, 'big')
    
    # Convert to Base58
    result = []
    for _ in range(22):
        num, remainder = divmod(num, 58)
        result.append(alphabet[remainder])
    
    return ''.join(reversed(result))


# =============================================================================
# PHARMA SCHEMA DEFINITIONS
# =============================================================================

# Entity types (extend GRC-20 system types)
ENTITY_TYPES = {
    "Ingredient": {
        "description": "Active pharmaceutical ingredient",
        "parent": "Type",
    },
    "ClinicalDrug": {
        "description": "Semantic clinical drug (SCD) - generic drug product",
        "parent": "Type",
    },
    "BrandedDrug": {
        "description": "Semantic branded drug (SBD) - branded drug product",
        "parent": "Type",
    },
    "BrandName": {
        "description": "Brand name for a drug",
        "parent": "Type",
    },
    "DoseForm": {
        "description": "Dosage form (tablet, capsule, injection, etc.)",
        "parent": "Type",
    },
    "NDC": {
        "description": "National Drug Code identifier",
        "parent": "Type",
    },
    "Provenance": {
        "description": "Data source provenance",
        "parent": "Type",
    },
    "Section": {
        "description": "Document section (e.g., drug label section)",
        "parent": "Type",
    },
    "DrugClass": {
        "description": "Drug classification or category",
        "parent": "Type",
    },
    "Relation": {
        "description": "GRC-20 relation entity (edge between nodes)",
        "parent": "Type",
    },
}

# All attributes with their value types
ATTRIBUTES = {
    # Core attributes
    "name": {
        "value_type": "TEXT",
        "description": "Primary name or label",
    },
    "rxcui": {
        "value_type": "TEXT",
        "description": "RxNorm Concept Unique Identifier",
    },
    "ndc_code": {
        "value_type": "TEXT",
        "description": "National Drug Code",
    },
    "tty": {
        "value_type": "TEXT",
        "description": "RxNorm Term Type",
    },
    "type": {
        "value_type": "TEXT",
        "description": "Entity type",
    },
    
    # Chemical properties
    "pubchem_cid": {
        "value_type": "NUMBER",
        "description": "PubChem Compound ID",
    },
    "smiles": {
        "value_type": "TEXT",
        "description": "SMILES molecular structure",
    },
    "inchikey": {
        "value_type": "TEXT",
        "description": "InChIKey identifier",
    },
    "iupac_name": {
        "value_type": "TEXT",
        "description": "IUPAC systematic name",
    },
    "molecular_formula": {
        "value_type": "TEXT",
        "description": "Molecular formula",
    },
    "molecular_weight": {
        "value_type": "NUMBER",
        "description": "Molecular weight in Daltons",
    },
    
    # Extended PubChem properties (to be added to schema)
    "pubchem_date": {
        "value_type": "TIME",
        "description": "PubChem data retrieval date",
    },
    "pmid": {
        "value_type": "TEXT",
        "description": "PubMed ID reference",
    },
    "sid": {
        "value_type": "TEXT",
        "description": "PubChem Substance ID",
    },
    "mesh_classes": {
        "value_type": "TEXT",
        "description": "MeSH classification codes",
    },
    
    # Provenance attributes
    "source": {
        "value_type": "TEXT",
        "description": "Data source name",
    },
    "citation": {
        "value_type": "TEXT",
        "description": "Citation for data source",
    },
    "date_accessed": {
        "value_type": "TIME",
        "description": "Date data was accessed",
    },
    "source_url": {
        "value_type": "URL",
        "description": "URL to data source",
    },
    "provenance_type": {
        "value_type": "TEXT",
        "description": "Type of provenance: AUTOMATED, EXPERT, INFERRED, IMPORTED",
    },
    
    # Section attributes
    "section_type": {
        "value_type": "TEXT",
        "description": "Type of document section",
    },
    "content": {
        "value_type": "TEXT",
        "description": "Text content",
    },
    "sequence": {
        "value_type": "NUMBER",
        "description": "Order sequence",
    },
    
    # Drug classification
    "class_name": {
        "value_type": "TEXT",
        "description": "Drug class name",
    },
    "class_type": {
        "value_type": "TEXT",
        "description": "Classification system (ATC, MeSH, etc.)",
    },
    "class_code": {
        "value_type": "TEXT",
        "description": "Classification code",
    },
    
    # Clinical attributes
    "clinical_weight": {
        "value_type": "NUMBER",
        "description": "Weighted clinical relationship for decision support",
    },
    "evidence": {
        "value_type": "TEXT",
        "description": "Evidence supporting a clinical relationship",
    },
}

# RxNorm relationship types - COMPREHENSIVE
# Based on RXNREL.RRF relationship types
RELATION_TYPES = {
    # Ingredient relationships
    "has_ingredient": {
        "description": "Drug has this ingredient",
        "inverse": "ingredient_of",
    },
    "ingredient_of": {
        "description": "Ingredient is in this drug",
        "inverse": "has_ingredient",
    },
    "has_precise_ingredient": {
        "description": "Drug has this precise ingredient (salt form)",
        "inverse": "precise_ingredient_of",
    },
    "precise_ingredient_of": {
        "description": "Precise ingredient is in this drug",
        "inverse": "has_precise_ingredient",
    },
    "has_ingredients": {
        "description": "Multiple ingredients drug has",
        "inverse": "ingredients_of",
    },
    "ingredients_of": {
        "description": "Ingredients are in this multiple ingredient drug",
        "inverse": "has_ingredients",
    },
    
    # Dose form relationships
    "has_dose_form": {
        "description": "Drug has this dose form",
        "inverse": "dose_form_of",
    },
    "dose_form_of": {
        "description": "Dose form is used by this drug",
        "inverse": "has_dose_form",
    },
    "has_doseformgroup": {
        "description": "Drug belongs to this dose form group",
        "inverse": "doseformgroup_of",
    },
    "doseformgroup_of": {
        "description": "Dose form group contains this drug",
        "inverse": "has_doseformgroup",
    },
    
    # Brand/tradename relationships
    "has_tradename": {
        "description": "Drug has this brand/trade name",
        "inverse": "tradename_of",
    },
    "tradename_of": {
        "description": "Brand name is for this drug",
        "inverse": "has_tradename",
    },
    "has_brand": {
        "description": "Drug has this brand",
        "inverse": "brand_of",
    },
    "brand_of": {
        "description": "Brand is for this drug",
        "inverse": "has_brand",
    },
    
    # Hierarchy relationships
    "is_a": {
        "description": "Entity is a subtype of",
        "inverse": "inverse_isa",
    },
    "inverse_isa": {
        "description": "Entity is a supertype of",
        "inverse": "is_a",
    },
    
    # Composition relationships
    "consists_of": {
        "description": "Drug consists of these components",
        "inverse": "constitutes",
    },
    "constitutes": {
        "description": "Component constitutes this drug",
        "inverse": "consists_of",
    },
    "contains": {
        "description": "Pack contains this drug",
        "inverse": "contained_in",
    },
    "contained_in": {
        "description": "Drug is contained in this pack",
        "inverse": "contains",
    },
    
    # Part relationships
    "has_part": {
        "description": "Entity has this part",
        "inverse": "part_of",
    },
    "part_of": {
        "description": "Entity is part of this",
        "inverse": "has_part",
    },
    "has_form": {
        "description": "Drug has this form (salt form)",
        "inverse": "form_of",
    },
    "form_of": {
        "description": "Form is of this drug",
        "inverse": "has_form",
    },
    
    # Reformulation relationships
    "reformulated_to": {
        "description": "Drug was reformulated to this",
        "inverse": "reformulation_of",
    },
    "reformulation_of": {
        "description": "Drug is a reformulation of this",
        "inverse": "reformulated_to",
    },
    
    # Quantified form relationships
    "has_quantified_form": {
        "description": "Drug has this quantified form",
        "inverse": "quantified_form_of",
    },
    "quantified_form_of": {
        "description": "Quantified form is of this drug",
        "inverse": "has_quantified_form",
    },
    
    # Boss relationship (active moiety)
    "has_boss": {
        "description": "Drug has this boss (active moiety)",
        "inverse": "boss_of",
    },
    "boss_of": {
        "description": "Boss (active moiety) of this drug",
        "inverse": "has_boss",
    },
    
    # Mapping relationships
    "equivalent_to": {
        "description": "Entity is equivalent to",
        "inverse": "equivalent_to",
    },
    "mapped_to": {
        "description": "Entity is mapped to",
        "inverse": "mapped_from",
    },
    "mapped_from": {
        "description": "Entity is mapped from",
        "inverse": "mapped_to",
    },
    
    # NDC relationships
    "has_ndc": {
        "description": "Drug has this NDC code",
        "inverse": "ndc_for",
    },
    "ndc_for": {
        "description": "NDC code is for this drug",
        "inverse": "has_ndc",
    },
    "maps_to_rxcui": {
        "description": "NDC maps to this RxCUI",
        "inverse": "mapped_from_ndc",
    },
    "mapped_from_ndc": {
        "description": "RxCUI is mapped from this NDC",
        "inverse": "maps_to_rxcui",
    },
    
    # Classification relationships
    "has_class": {
        "description": "Drug has this classification",
        "inverse": "class_of",
    },
    "class_of": {
        "description": "Classification includes this drug",
        "inverse": "has_class",
    },
    
    # Document relationships
    "has_section": {
        "description": "Document has this section",
        "inverse": "section_of",
    },
    "section_of": {
        "description": "Section is part of this document",
        "inverse": "has_section",
    },
    "belongs_to_drug": {
        "description": "Section belongs to this drug",
        "inverse": "has_label_section",
    },
    "has_label_section": {
        "description": "Drug has this label section",
        "inverse": "belongs_to_drug",
    },
    
    # Provenance relationships
    "has_provenance": {
        "description": "Entity has this provenance",
        "inverse": "provenance_of",
    },
    "provenance_of": {
        "description": "Provenance is for this entity",
        "inverse": "has_provenance",
    },
    "has_source": {
        "description": "Entity has this source",
        "inverse": "source_of",
    },
    "source_of": {
        "description": "Source is for this entity",
        "inverse": "has_source",
    },
    
    # Clinical relationships
    "curated_by": {
        "description": "Relationship curated by",
        "inverse": "curated",
    },
    "curated": {
        "description": "Curated this relationship",
        "inverse": "curated_by",
    },
    "alternative_for": {
        "description": "Alternative drug for",
        "inverse": "has_alternative",
    },
    "has_alternative": {
        "description": "Has alternative drug",
        "inverse": "alternative_for",
    },
    "has_evidence": {
        "description": "Has supporting evidence",
        "inverse": "evidence_for",
    },
    "evidence_for": {
        "description": "Evidence for this relationship",
        "inverse": "has_evidence",
    },
    "weights": {
        "description": "Clinical weight for this relationship",
        "inverse": "weighted_by",
    },
    "weighted_by": {
        "description": "Weighted by this evidence",
        "inverse": "weights",
    },
}


class PharmaSchema:
    """
    Pharma Knowledge Graph Schema.
    
    Manages entity types, attributes, and relation types.
    Generates and caches GRC-20 compliant IDs.
    """
    
    CACHE_FILE = Path(__file__).parent / "schema_cache.json"
    
    def __init__(self):
        self.types: Dict[str, str] = {}
        self.attributes: Dict[str, str] = {}
        self.relations: Dict[str, str] = {}
        self.metadata: Dict[str, Any] = {}
        
        # Try to load from cache
        if not self._load_cache():
            # Generate new IDs
            self._generate_ids()
            self._save_cache()
        
        # Print cache info
        print(f"Loaded schema v{self.metadata.get('version', '?.?.?')} from cache")
    
    def _load_cache(self) -> bool:
        """Load schema from cache file."""
        if not self.CACHE_FILE.exists():
            return False
        
        try:
            with open(self.CACHE_FILE, 'r') as f:
                data = json.load(f)
            
            self.types = data.get("types", {})
            self.attributes = data.get("attributes", {})
            self.relations = data.get("relations", {})
            self.metadata = data.get("metadata", {})
            
            return True
        except Exception:
            return False
    
    def _generate_ids(self):
        """Generate GRC-20 IDs for all schema elements."""
        self.metadata = {
            "version": "1.1.0",
            "created": __import__('datetime').datetime.now().isoformat(),
            "description": "Pharma Knowledge Graph Schema",
        }
        
        # Generate type IDs
        for type_name in ENTITY_TYPES:
            self.types[type_name] = generate_grc20_id(seed=f"pharma_type_{type_name}")
        
        # Generate attribute IDs
        for attr_name in ATTRIBUTES:
            self.attributes[attr_name] = generate_grc20_id(seed=f"pharma_attr_{attr_name}")
        
        # Generate relation type IDs
        for rel_name in RELATION_TYPES:
            self.relations[rel_name] = generate_grc20_id(seed=f"pharma_rel_{rel_name}")
    
    def _save_cache(self):
        """Save schema to cache file."""
        data = {
            "metadata": self.metadata,
            "types": self.types,
            "attributes": self.attributes,
            "relations": self.relations,
        }
        
        with open(self.CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def attr(self, name: str) -> str:
        """Get GRC-20 ID for an attribute."""
        # Check GRC-20 implicit attributes first
        if name in GRC20_IMPLICIT_ATTRIBUTES:
            return GRC20_IMPLICIT_ATTRIBUTES[name]
        if name in GRC20_RELATION_ATTRIBUTES:
            return GRC20_RELATION_ATTRIBUTES[name]
        
        if name not in self.attributes:
            raise KeyError(f"Unknown attribute: {name}")
        return self.attributes[name]
    
    def rel(self, name: str) -> str:
        """Get GRC-20 ID for a relation type."""
        if name not in self.relations:
            raise KeyError(f"Unknown relation: {name}")
        return self.relations[name]
    
    def type_id(self, name: str) -> str:
        """Get GRC-20 ID for an entity type."""
        if name not in self.types:
            raise KeyError(f"Unknown type: {name}")
        return self.types[name]
    
    def triple(self, entity_id: str, attribute: str, value: Any, value_type: str = None) -> dict:
        """
        Create a GRC-20 triple.
        
        Args:
            entity_id: The entity ID
            attribute: Attribute name (will be converted to ID)
            value: The value
            value_type: Optional value type override
        
        Returns:
            Dict representing a GRC-20 triple
        """
        attr_id = self.attr(attribute)
        
        # Determine value type
        if value_type is None:
            value_type = ATTRIBUTES.get(attribute, {}).get("value_type", "TEXT")
        
        # Map value types to GRC-20 type numbers
        type_map = {
            "TEXT": 1,
            "NUMBER": 2,
            "CHECKBOX": 3,
            "URL": 4,
            "TIME": 5,
            "POINT": 6,
        }
        
        grc_type = type_map.get(value_type.upper(), 1)
        
        return {
            "entity": entity_id,
            "attribute": attr_id,
            "value": {
                "type": grc_type,
                "value": str(value) if value is not None else "",
            }
        }
    
    def relation(
        self,
        from_entity: str,
        relation_type: str,
        to_entity: str,
        relation_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Create a GRC-20 relation (returns list of triples).
        
        In GRC-20, relations are entities with from_entity and to_entity attributes.
        
        Args:
            from_entity: Source entity ID
            relation_type: Type of relation
            to_entity: Target entity ID
            relation_id: Optional ID for the relation entity
        
        Returns:
            List of triples representing this relation
        """
        if relation_id is None:
            relation_id = generate_grc20_id()
        
        rel_type_id = self.rel(relation_type)
        
        triples = [
            # The relation IS A type (Relations are entities with type)
            {
                "entity": relation_id,
                "attribute": GRC20_SYSTEM_TYPES["Type"],
                "value": {"type": 1, "value": rel_type_id},
            },
            # The relation IS A Relation (subclass of Type)
            {
                "entity": relation_id,
                "attribute": GRC20_SYSTEM_TYPES["Type"],
                "value": {"type": 1, "value": GRC20_SYSTEM_TYPES["Relation"]},
            },
            # From entity
            {
                "entity": relation_id,
                "attribute": GRC20_RELATION_ATTRIBUTES["from_entity"],
                "value": {"type": 1, "value": from_entity},
            },
            # To entity
            {
                "entity": relation_id,
                "attribute": GRC20_RELATION_ATTRIBUTES["to_entity"],
                "value": {"type": 1, "value": to_entity},
            },
        ]
        
        return triples
    

    def create_entity(
        self,
        entity_type: str,
        name: str,
        entity_id: Optional[str] = None,
    ) -> dict:
        """
        Create a GRC-20 entity (returns dict with entity_id and triples).
        
        Args:
            entity_type: Type of entity (e.g., "Ingredient", "ClinicalDrug")
            name: Primary name for the entity
            entity_id: Optional ID for the entity (auto-generated if not provided)
        
        Returns:
            Dict with 'entity' (entity_id) and 'triples' list
        """
        if entity_id is None:
            entity_id = generate_grc20_id()
        
        type_id = self.types.get(entity_type)
        
        triples = []
        
        # Add type triple
        if type_id:
            triples.append({
                "entity": entity_id,
                "attribute": GRC20_SYSTEM_TYPES["Type"],
                "value": {"type": 1, "value": type_id},
            })
        
        # Add name triple
        triples.append(self.triple(entity_id, "name", name))
        
        return {
            "entity": entity_id,
            "triples": triples,
        }

    def get_attr_name(self, attr_id: str) -> Optional[str]:
        """Reverse lookup: Get attribute name from ID."""
        for name, id_ in self.attributes.items():
            if id_ == attr_id:
                return name
        # Check GRC-20 implicit attributes
        for name, id_ in GRC20_IMPLICIT_ATTRIBUTES.items():
            if id_ == attr_id:
                return name
        for name, id_ in GRC20_RELATION_ATTRIBUTES.items():
            if id_ == attr_id:
                return name
        return None
    
    def get_rel_name(self, rel_id: str) -> Optional[str]:
        """Reverse lookup: Get relation name from ID."""
        for name, id_ in self.relations.items():
            if id_ == rel_id:
                return name
        return None
    
    def create_provenance(
        self,
        source: str,
        citation: str,
        date_accessed: str,
        source_url: str = None,
        provenance_type: str = "IMPORTED",
    ) -> dict:
        """
        Create a provenance entity.
        
        Returns:
            Dict with entity_id and triples
        """
        entity_id = generate_grc20_id(seed=f"prov_{source}_{date_accessed}")
        
        triples = [
            self.triple(entity_id, "type", "Provenance"),
            self.triple(entity_id, "name", f"{source} - {date_accessed}"),
            self.triple(entity_id, "source", source),
            self.triple(entity_id, "citation", citation),
            self.triple(entity_id, "date_accessed", date_accessed),
        ]
        
        if source_url:
            triples.append(self.triple(entity_id, "source_url", source_url))
        
        triples.append(self.triple(entity_id, "provenance_type", provenance_type))
        
        return {
            "entity_id": entity_id,
            "triples": triples,
        }
    
    def summary(self) -> str:
        """Return a summary of the schema."""
        lines = [
            f"Pharma Schema v{self.metadata.get('version', '?.?.?')}",
            f"  Types: {len(self.types)}",
            f"  Attributes: {len(self.attributes)}",
            f"  Relations: {len(self.relations)}",
        ]
        
        lines.append(f"\nEntity Types ({len(self.types)}):")
        for name, id_ in list(self.types.items())[:5]:
            lines.append(f"  {name}: {id_}")
        lines.append(f"  ... and {len(self.types) - 5} more")
        
        lines.append(f"\nAttributes ({len(self.attributes)}):")
        for name, id_ in list(self.attributes.items())[:5]:
            lines.append(f"  {name}: {id_}")
        lines.append(f"  ... and {len(self.attributes) - 5} more")
        
        lines.append(f"\nRelation Types ({len(self.relations)}):")
        for name, id_ in list(self.relations.items())[:5]:
            lines.append(f"  {name}: {id_}")
        lines.append(f"  ... and {len(self.relations) - 5} more")
        
        return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pharma Schema CLI")
    parser.add_argument("--clear-cache", action="store_true", help="Clear schema cache")
    parser.add_argument("--list-types", action="store_true", help="List all entity types")
    parser.add_argument("--list-attrs", action="store_true", help="List all attributes")
    parser.add_argument("--list-rels", action="store_true", help="List all relations")
    parser.add_argument("--summary", action="store_true", help="Show schema summary")
    args = parser.parse_args()
    
    if args.clear_cache:
        if PharmaSchema.CACHE_FILE.exists():
            PharmaSchema.CACHE_FILE.unlink()
            print("Cache cleared")
    
    schema = PharmaSchema()
    
    if args.list_types:
        print("\nEntity Types:")
        for name, id_ in schema.types.items():
            desc = ENTITY_TYPES.get(name, {}).get("description", "")
            print(f"  {name}: {id_}")
            print(f"    {desc}")
    
    if args.list_attrs:
        print("\nAttributes:")
        for name, id_ in schema.attributes.items():
            info = ATTRIBUTES.get(name, {})
            print(f"  {name}: {id_}")
            print(f"    Type: {info.get('value_type', 'TEXT')}")
            print(f"    {info.get('description', '')}")
    
    if args.list_rels:
        print("\nRelation Types:")
        for name, id_ in schema.relations.items():
            info = RELATION_TYPES.get(name, {})
            print(f"  {name}: {id_}")
            print(f"    {info.get('description', '')}")
            if info.get("inverse"):
                print(f"    Inverse: {info['inverse']}")
    
    if args.summary or not any([args.list_types, args.list_attrs, args.list_rels]):
        print(schema.summary())
