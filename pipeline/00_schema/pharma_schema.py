#!/usr/bin/env python3
"""
Pharma Knowledge Graph Schema v3.0
==================================

GRC-20 compliant schema aligned with RxNorm TTY structure.

This is a backward-compatible superset that:
- Maps RxNorm TTYs 1:1 to entity types (v3 feature)
- Preserves all v2 entity types and relation types
- Extended method signatures with optional parameters

Key Changes from v2:
- Entity types now map 1:1 to RxNorm TTYs (new types added)
- Relations include rela_code, source_tty, target_tty attributes
- Relation types derived from TTY combinations
- Simplified attribute set (removed IsActive, Suppress)
- Added tty_to_entity_type() helper
- Added get_relation_type_for_tty_pair() helper
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
    "type": "Jfmby78N4BCseZinBmdVov",
    "description": "LA1DqP5v6QAdsgLPXGF3YA",
}

# =============================================================================
# RXNORM TTY TO ENTITY TYPE MAPPING (v3)
# =============================================================================

TTY_TO_ENTITY_TYPE = {
    # Ingredients
    "IN":   "Ingredient",
    "PIN":  "PreciseIngredient",
    "MIN":  "MultipleIngredient",
    "SU":   "SpecificSubstance",
    
    # Clinical Drug Components (Generic)
    "SCDC": "ClinicalDrugComponent",
    "SCDF": "ClinicalDrugForm",
    "SCDG": "ClinicalDrugGroup",
    "SCDGP":"ClinicalDrugGroupPrecise",
    "SCD":  "ClinicalDrug",
    
    # Branded Drug Components
    "SBDC": "BrandedDrugComponent",
    "SBDF": "BrandedDrugForm",
    "SBDG": "BrandedDrugGroup",
    "SBD":  "BrandedDrug",
    
    # Brand Names
    "BN":   "BrandName",
    
    # Dose Forms
    "DF":   "DoseForm",
    "DFG":  "DoseFormGroup",
    
    # Packs
    "GPCK": "GenericPack",
    "BPCK": "BrandPack",
    
    # Names
    "PSN":  "PrescribableName",
    "SY":   "Synonym",
    "TMSY": "TallManSynonym",
    
    # External mappings
    "DP":   "DrugProduct",
    "MTH_RXN_DP": "MTHDrugProduct",
}

# =============================================================================
# RELATION TYPE DEFINITIONS - Derived from TTY combinations (v3)
# =============================================================================

RELATION_TYPE_DEFINITIONS = {
    # Ingredient → Component/Form/Group (RO relationships)
    "has_component": {
        "description": "Ingredient has clinical drug component",
        "from_tty": ["IN"],
        "to_tty": ["SCDC"],
        "rela_code": "RO",
        "inverse": "ingredient_of"
    },
    "has_form": {
        "description": "Ingredient has clinical drug form",
        "from_tty": ["IN"],
        "to_tty": ["SCDF"],
        "rela_code": "RO",
        "inverse": "form_of"
    },
    "has_group": {
        "description": "Ingredient has clinical drug group",
        "from_tty": ["IN"],
        "to_tty": ["SCDG"],
        "rela_code": "RO",
        "inverse": "group_of"
    },
    
    # Reverse: Component/Form/Group → Ingredient
    "ingredient_of": {
        "description": "Component/form/group has this ingredient",
        "from_tty": ["SCDC", "SCDF", "SCDG"],
        "to_tty": ["IN"],
        "rela_code": "RO",
        "inverse": "has_component"
    },
    
    # Component/Form/Group → ClinicalDrug (RO/RN relationships)
    "has_clinical_drug": {
        "description": "Component/form/group has clinical drug",
        "from_tty": ["SCDC", "SCDF", "SCDG"],
        "to_tty": ["SCD"],
        "rela_code": "RO,RN",
        "inverse": "clinical_drug_of"
    },
    
    # ClinicalDrug → BrandedDrug (RN relationship)
    "has_branded_drug": {
        "description": "Clinical drug has branded drug",
        "from_tty": ["SCD"],
        "to_tty": ["SBD"],
        "rela_code": "RN",
        "inverse": "branded_drug_of"
    },
    
    # Component/Form/Group → Branded variants (RN relationships)
    "has_branded_component": {
        "description": "Clinical component has branded component",
        "from_tty": ["SCDC"],
        "to_tty": ["SBDC"],
        "rela_code": "RN",
        "inverse": "branded_component_of"
    },
    "has_branded_form": {
        "description": "Clinical form has branded form",
        "from_tty": ["SCDF"],
        "to_tty": ["SBDF"],
        "rela_code": "RN",
        "inverse": "branded_form_of"
    },
    "has_branded_group": {
        "description": "Clinical group has branded group",
        "from_tty": ["SCDG"],
        "to_tty": ["SBDG"],
        "rela_code": "RN",
        "inverse": "branded_group_of"
    },
    
    # Brand connections (RN/RO relationships)
    "has_brand_name": {
        "description": "Entity has brand name",
        "from_tty": ["IN", "PIN"],
        "to_tty": ["BN"],
        "rela_code": "RN",
        "inverse": "brand_name_of"
    },
    "has_brand": {
        "description": "Branded drug has brand",
        "from_tty": ["SBD", "SBDC", "SBDF", "SBDG"],
        "to_tty": ["BN"],
        "rela_code": "RO",
        "inverse": "brand_of"
    },
    
    # Precise ingredient relationships
    "has_precise_ingredient": {
        "description": "Ingredient has precise ingredient (salt form)",
        "from_tty": ["IN"],
        "to_tty": ["PIN"],
        "rela_code": "RN",
        "inverse": "precise_ingredient_of"
    },
}

# =============================================================================
# ENTITY TYPE DEFINITIONS
# =============================================================================

ENTITY_TYPES = {
    # RxNorm TTY-based types (v3 expanded)
    "Ingredient": {"description": "Active pharmaceutical ingredient (IN)", "tty": "IN"},
    "PreciseIngredient": {"description": "Precise ingredient - salt form (PIN)", "tty": "PIN"},
    "MultipleIngredient": {"description": "Multiple ingredient combination (MIN)", "tty": "MIN"},
    "SpecificSubstance": {"description": "Specific substance (SU)", "tty": "SU"},
    
    "ClinicalDrugComponent": {"description": "Semantic Clinical Drug Component (SCDC)", "tty": "SCDC"},
    "ClinicalDrugForm": {"description": "Semantic Clinical Drug Form (SCDF)", "tty": "SCDF"},
    "ClinicalDrugGroup": {"description": "Semantic Clinical Drug Group (SCDG)", "tty": "SCDG"},
    "ClinicalDrugGroupPrecise": {"description": "Semantic Clinical Drug Group Precise (SCDGP)", "tty": "SCDGP"},
    "ClinicalDrug": {"description": "Semantic Clinical Drug (SCD)", "tty": "SCD"},
    
    "BrandedDrugComponent": {"description": "Semantic Branded Drug Component (SBDC)", "tty": "SBDC"},
    "BrandedDrugForm": {"description": "Semantic Branded Drug Form (SBDF)", "tty": "SBDF"},
    "BrandedDrugGroup": {"description": "Semantic Branded Drug Group (SBDG)", "tty": "SBDG"},
    "BrandedDrug": {"description": "Semantic Branded Drug (SBD)", "tty": "SBD"},
    
    "BrandName": {"description": "Brand name for a drug (BN)", "tty": "BN"},
    
    "DoseForm": {"description": "Dosage form (DF)", "tty": "DF"},
    "DoseFormGroup": {"description": "Dose form group (DFG)", "tty": "DFG"},
    
    "GenericPack": {"description": "Generic pack (GPCK)", "tty": "GPCK"},
    "BrandPack": {"description": "Brand pack (BPCK)", "tty": "BPCK"},
    
    "PrescribableName": {"description": "Prescribable name (PSN)", "tty": "PSN"},
    "Synonym": {"description": "Synonym (SY)", "tty": "SY"},
    "TallManSynonym": {"description": "Tall man synonym (TMSY)", "tty": "TMSY"},
    
    "DrugProduct": {"description": "Drug product (NDDF DP)", "tty": "DP"},
    "MTHDrugProduct": {"description": "MTH drug product", "tty": "MTH_RXN_DP"},
    
    # Non-RxNorm types (preserved from v2)
    "PackageInsert": {"description": "FDA drug label/package insert document", "tty": None},
    "Manufacturer": {"description": "Drug manufacturer or labeler company", "tty": None},
    "NDC": {"description": "National Drug Code identifier", "tty": None},
    "Provenance": {"description": "Data source provenance", "tty": None},
    "Section": {"description": "Document section (e.g., drug label section)", "tty": None},
    "DrugClass": {"description": "Drug classification or category", "tty": None},
    
    # GRC-20 system type
    "Relation": {"description": "GRC-20 relation entity (edge between nodes)", "tty": None},
}

# =============================================================================
# ATTRIBUTE DEFINITIONS
# =============================================================================

ATTRIBUTES = {
    # Core attributes
    "name": {"value_type": "TEXT", "description": "Primary name or label"},
    "rxcui": {"value_type": "TEXT", "description": "RxNorm Concept Unique Identifier"},
    "tty": {"value_type": "TEXT", "description": "RxNorm Term Type"},
    
    # Relation attributes (v3 - for storing on relation entities)
    "rela_code": {"value_type": "TEXT", "description": "Raw RxNorm relationship code (RO/RN/RB)"},
    "source_tty": {"value_type": "TEXT", "description": "Source term type for relationship"},
    "target_tty": {"value_type": "TEXT", "description": "Target term type for relationship"},
    
    # Chemical properties
    "pubchem_cid": {"value_type": "NUMBER", "description": "PubChem Compound ID"},
    "smiles": {"value_type": "TEXT", "description": "SMILES molecular structure"},
    "inchikey": {"value_type": "TEXT", "description": "InChIKey identifier"},
    "iupac_name": {"value_type": "TEXT", "description": "IUPAC systematic name"},
    "molecular_formula": {"value_type": "TEXT", "description": "Molecular formula"},
    "molecular_weight": {"value_type": "NUMBER", "description": "Molecular weight in Daltons"},
    
    # DailyMed / Package Insert attributes
    "ndc_code": {"value_type": "TEXT", "description": "National Drug Code"},
    "fda_set_id": {"value_type": "TEXT", "description": "FDA SET ID for package insert"},
    "effective_time": {"value_type": "TIME", "description": "Effective date/time of drug label"},
    "content": {"value_type": "TEXT", "description": "Text content of a document section"},
    "set_id": {"value_type": "TEXT", "description": "Unique identifier for document set"},
    
    # PubChem attributes
    "pubchem_date": {"value_type": "TIME", "description": "PubChem data retrieval date"},
    "pmid": {"value_type": "TEXT", "description": "PubMed ID reference"},
    "sid": {"value_type": "TEXT", "description": "PubChem Substance ID"},
    "mesh_classes": {"value_type": "TEXT", "description": "MeSH classification codes"},
    
    # Provenance attributes
    "source": {"value_type": "TEXT", "description": "Data source name"},
    "citation": {"value_type": "TEXT", "description": "Citation for data source"},
    "date_accessed": {"value_type": "TIME", "description": "Date data was accessed"},
    "source_url": {"value_type": "URL", "description": "URL to data source"},
    "provenance_type": {"value_type": "TEXT", "description": "Type of provenance: AUTOMATED, EXPERT, INFERRED, IMPORTED"},
    "provenance": {"value_type": "TEXT", "description": "Link to provenance entity ID"},
    
    # Section attributes
    "section_type": {"value_type": "TEXT", "description": "Type of document section"},
    "sequence": {"value_type": "NUMBER", "description": "Order sequence"},
    
    # Drug classification
    "class_name": {"value_type": "TEXT", "description": "Drug class name"},
    "class_type": {"value_type": "TEXT", "description": "Classification system (ATC, MeSH, etc.)"},
    "class_code": {"value_type": "TEXT", "description": "Classification code"},
    
    # Clinical attributes (preserved from v2)
    "clinical_weight": {"value_type": "NUMBER", "description": "Weighted clinical relationship for decision support"},
    "evidence": {"value_type": "TEXT", "description": "Evidence supporting a clinical relationship"},
}

# =============================================================================
# RELATION TYPE IDS - Preserved from existing data
# =============================================================================

GRC20_RELATION_TYPE_IDS = {
    # Existing relation types (preserved for backward compatibility)
    'boss_of': 'P7QWFVWRq7UW135x1mafhi',
    'consists_of': '47hNRekccKsRb7ruguT4cF',
    'constitutes': 'ThJY6kbZCnNicvmYpjSvQL',
    'contained_in': '4YuUjJksi6zxV1dLoY6oZU',
    'contains': '1xW9AWXgREdeEuQjE3XMkg',
    'dose_form_of': 'XpPqGMbFs3nkD2f1E7kEQv',
    'doseformgroup_of': '1nkBDMtbUJ6Vmu2FL9r4Mv',
    'equivalent_to': 'XmAN7VHELDoBiFJdTcfa3J',
    'form_of': '4j218PDp8FQ6qGMcDLBtcy',
    'has_boss': 'FQTxU4WdHw5e5QmmQvB35T',
    'has_dose_form': 'PP85FvUeKf7dyyezyFZfpJ',
    'has_doseformgroup': 'McfVwPmrZuon3m6PBPRAMs',
    'has_form': 'X5oGrGrPzBeV4atDLzFHqj',
    'has_ingredient': 'D5AVoQ3STThZQbyyArhmKp',
    'has_ingredients': 'GcWhxQ6dUfNEdT1o6jv6E7',
    'has_part': 'VQscBJ5vnJ5JtDDuErern6',
    'has_precise_ingredient': '7CaCTZ4rZc4wRBfNzmG8PF',
    'has_provenance': 'EeBN13RVEArKqPkiJyaehN',
    'has_quantified_form': 'E7RAaop29vbtgf47FeDM4a',
    'has_section': '5Mt7Vm4DbzwM8nV33k7hUz',
    'has_tradename': 'NQNgJnZhnruRPJNFf5FJ8U',
    'ingredient_of': 'CyxEJZRAXsSE6GcCLV3SwL',
    'ingredients_of': 'GrQowXGofpiTcAFToQz7DZ',
    'inverse_isa': 'BwCWDZSxSCQGjBL8XmtVKw',
    'is_a': 'PJVaAAcDxuZMjDQp6RDWPT',
    'manufactured_by': 'RdBtXGtjxpgV8W3Lq8Vpyi',
    'maps_to_rxcui': 'U8MJJF4TbUWfKx6V47iBc6',
    'part_of': 'Q6H7LuDQ8DCoxRxYKA6VSU',
    'precise_ingredient_of': 'TwGRTEr9tF3Fzhje2xdat2',
    'quantified_form_of': 'CXBn4nxA5c9UmiEFjayY7Y',
    'reformulated_to': 'VHFjJ24bjWQDxLF8eozSJ8',
    'reformulation_of': 'W9YqhQbBrigaDZDWU7ocr2',
    'tradename_of': 'S8TsYkEAJb6ahkvS65i6vG',
    
    # v3 TTY-based relation types (will be generated if not present)
    'has_component': None,
    'has_group': None,
    'has_clinical_drug': None,
    'has_branded_drug': None,
    'has_branded_component': None,
    'has_branded_form': None,
    'has_branded_group': None,
    'has_brand_name': None,
    'has_brand': None,
    'brand_name_of': None,
    'brand_of': None,
    'clinical_drug_of': None,
    'branded_drug_of': None,
    'group_of': None,
    'branded_component_of': None,
    'branded_form_of': None,
    'branded_group_of': None,
}

# =============================================================================
# RELATION TYPES - Full definitions (v2 preserved + v3 additions)
# =============================================================================

RELATION_TYPES = {
    # Document structure (v2)
    "has_section": {"description": "Package insert has this section", "from_type": "PackageInsert", "to_type": "Section", "inverse": "section_of"},
    "section_of": {"description": "Section belongs to this package insert", "from_type": "Section", "to_type": "PackageInsert", "inverse": "has_section"},
    "manufactured_by": {"description": "Package insert manufactured by this company", "from_type": "PackageInsert", "to_type": "Manufacturer", "inverse": "manufactures"},
    "manufactures": {"description": "Manufacturer produces this drug product", "from_type": "Manufacturer", "to_type": "PackageInsert", "inverse": "manufactured_by"},
    
    # Ingredient relationships (v2)
    "has_ingredient": {"description": "Drug has this ingredient", "inverse": "ingredient_of"},
    "ingredient_of": {"description": "Ingredient is in this drug", "inverse": "has_ingredient"},
    "has_precise_ingredient": {"description": "Drug has this precise ingredient (salt form)", "inverse": "precise_ingredient_of"},
    "precise_ingredient_of": {"description": "Precise ingredient is in this drug", "inverse": "has_precise_ingredient"},
    "has_ingredients": {"description": "Multiple ingredients drug has", "inverse": "ingredients_of"},
    "ingredients_of": {"description": "Ingredients are in this multiple ingredient drug", "inverse": "has_ingredients"},
    
    # Dose form relationships (v2)
    "has_dose_form": {"description": "Drug has this dose form", "inverse": "dose_form_of"},
    "dose_form_of": {"description": "Dose form is used by this drug", "inverse": "has_dose_form"},
    "has_doseformgroup": {"description": "Drug belongs to this dose form group", "inverse": "doseformgroup_of"},
    "doseformgroup_of": {"description": "Dose form group contains this drug", "inverse": "has_doseformgroup"},
    
    # Brand relationships (v2)
    "has_tradename": {"description": "Drug has this brand/trade name", "inverse": "tradename_of"},
    "tradename_of": {"description": "Brand name is for this drug", "inverse": "has_tradename"},
    
    # Taxonomy relationships (v2)
    "is_a": {"description": "Entity is a subtype of", "inverse": "inverse_isa"},
    "inverse_isa": {"description": "Entity is a supertype of", "inverse": "is_a"},
    
    # Component relationships (v2)
    "consists_of": {"description": "Drug consists of these components", "inverse": "constitutes"},
    "constitutes": {"description": "Component constitutes this drug", "inverse": "consists_of"},
    "contains": {"description": "Pack contains this drug", "inverse": "contained_in"},
    "contained_in": {"description": "Drug is contained in this pack", "inverse": "contains"},
    "has_part": {"description": "Entity has this part", "inverse": "part_of"},
    "part_of": {"description": "Entity is part of this", "inverse": "has_part"},
    
    # Form relationships (v2)
    "has_form": {"description": "Drug has this form (salt form)", "inverse": "form_of"},
    "form_of": {"description": "Form is of this drug", "inverse": "has_form"},
    "reformulated_to": {"description": "Drug was reformulated to this", "inverse": "reformulation_of"},
    "reformulation_of": {"description": "Drug is a reformulation of this", "inverse": "reformulated_to"},
    "has_quantified_form": {"description": "Drug has this quantified form", "inverse": "quantified_form_of"},
    "quantified_form_of": {"description": "Quantified form is of this drug", "inverse": "has_quantified_form"},
    
    # Boss relationships (v2)
    "has_boss": {"description": "Drug has this boss (active moiety)", "inverse": "boss_of"},
    "boss_of": {"description": "Boss (active moiety) of this drug", "inverse": "has_boss"},
    
    # Equivalence (v2)
    "equivalent_to": {"description": "Entity is equivalent to", "inverse": "equivalent_to"},
    
    # NDC mapping (v2)
    "maps_to_rxcui": {"description": "NDC maps to this RxCUI", "inverse": "mapped_from_ndc"},
    "mapped_from_ndc": {"description": "RxCUI is mapped from this NDC", "inverse": "maps_to_rxcui"},
    
    # Provenance (v2)
    "has_provenance": {"description": "Entity has provenance information", "inverse": None},
    
    # v3 TTY-based relationships
    "has_component": {"description": "Ingredient has clinical drug component", "inverse": "ingredient_of"},
    "has_group": {"description": "Ingredient has clinical drug group", "inverse": "group_of"},
    "group_of": {"description": "Clinical drug group of this ingredient", "inverse": "has_group"},
    "has_clinical_drug": {"description": "Component/form/group has clinical drug", "inverse": "clinical_drug_of"},
    "clinical_drug_of": {"description": "Clinical drug of this component", "inverse": "has_clinical_drug"},
    "has_branded_drug": {"description": "Clinical drug has branded drug", "inverse": "branded_drug_of"},
    "branded_drug_of": {"description": "Branded drug of this clinical drug", "inverse": "has_branded_drug"},
    "has_branded_component": {"description": "Clinical component has branded component", "inverse": "branded_component_of"},
    "branded_component_of": {"description": "Branded component of this clinical component", "inverse": "has_branded_component"},
    "has_branded_form": {"description": "Clinical form has branded form", "inverse": "branded_form_of"},
    "branded_form_of": {"description": "Branded form of this clinical form", "inverse": "has_branded_form"},
    "has_branded_group": {"description": "Clinical group has branded group", "inverse": "branded_group_of"},
    "branded_group_of": {"description": "Branded group of this clinical group", "inverse": "has_branded_group"},
    "has_brand_name": {"description": "Entity has brand name", "inverse": "brand_name_of"},
    "brand_name_of": {"description": "Brand name of this entity", "inverse": "has_brand_name"},
    "has_brand": {"description": "Branded drug has brand", "inverse": "brand_of"},
    "brand_of": {"description": "Brand of this branded drug", "inverse": "has_brand"},
}


def generate_grc20_id(seed: str = None) -> str:
    """Generate a valid GRC-20 ID (22 character Base58)."""
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    
    if seed:
        hash_bytes = hashlib.md5(seed.encode()).digest()
        uuid_bytes = uuid.UUID(bytes=hash_bytes).bytes
    else:
        uuid_bytes = uuid.uuid4().bytes
    
    num = int.from_bytes(uuid_bytes, 'big')
    result = []
    for _ in range(22):
        num, remainder = divmod(num, 58)
        result.append(alphabet[remainder])
    
    return ''.join(reversed(result))


class PharmaSchema:
    """Pharma Knowledge Graph Schema v3 - GRC-20 Aligned with RxNorm TTY."""
    
    CACHE_FILE = Path(__file__).parent / "schema_cache.json"
    
    def __init__(self):
        self.types: Dict[str, str] = {}
        self.attributes: Dict[str, str] = {}
        self.relations: Dict[str, str] = {}
        self.metadata: Dict[str, Any] = {}
        
        if not self._load_cache():
            self._generate_ids()
            self._save_cache()
    
    def _load_cache(self) -> bool:
        print(f"[DEBUG] Checking for cache at: {self.CACHE_FILE}")
        if not self.CACHE_FILE.exists():
            print("[DEBUG] Cache NOT found. Will generate NEW IDs.")
            return False
        try:
            with open(self.CACHE_FILE, 'r') as f:
                data = json.load(f)
            self.types = data.get("types", {})
            self.attributes = data.get("attributes", {})
            self.relations = data.get("relations", {})
            self.metadata = data.get("metadata", {})
            prov_id = self.attributes.get("provenance", "MISSING")
            print(f"[DEBUG] Cache FOUND. Types: {len(self.types)}, Attrs: {len(self.attributes)}, Rels: {len(self.relations)}")
            print(f"[DEBUG] Provenance ID: {prov_id}")
            return True
        except Exception as e:
            print(f"[DEBUG] Cache found but failed to load: {e}")
            return False
    
    def _generate_ids(self):
        print("[DEBUG] Generating NEW IDs from scratch...")
        self.metadata = {
            "version": "3.0.0",
            "created": __import__('datetime').datetime.now().isoformat(),
            "description": "Pharma Knowledge Graph Schema v3 - TTY Aligned (backward compatible)",
        }
        
        # GRC-20 STANDARD ATTRIBUTE IDs
        STANDARD_ATTRIBUTE_IDS = {
            "name": "LuBWqZAu6pz54eiJS5mLv8",
            "type": "Jfmby78N4BCseZinBmdVov",
            "provenance": "LA1DqP5v6QAdsgLPXGF3YA",
        }
        
        # Generate type IDs
        for type_name in ENTITY_TYPES:
            self.types[type_name] = generate_grc20_id(seed=f"pharma_v3_type_{type_name}")
        
        # Generate attribute IDs
        for attr_name in ATTRIBUTES:
            if attr_name in STANDARD_ATTRIBUTE_IDS:
                self.attributes[attr_name] = STANDARD_ATTRIBUTE_IDS[attr_name]
                print(f"[DEBUG] Setting '{attr_name}' to FIXED ID: {self.attributes[attr_name]}")
            else:
                self.attributes[attr_name] = generate_grc20_id(seed=f"pharma_v3_attr_{attr_name}")
        
        # Use existing relation type IDs where available
        for rel_name in RELATION_TYPES:
            if rel_name in GRC20_RELATION_TYPE_IDS and GRC20_RELATION_TYPE_IDS[rel_name]:
                self.relations[rel_name] = GRC20_RELATION_TYPE_IDS[rel_name]
            else:
                self.relations[rel_name] = generate_grc20_id(seed=f"pharma_v3_rel_{rel_name}")
        
        print(f"[DEBUG] Generated {len(self.types)} types, {len(self.attributes)} attributes, {len(self.relations)} relations")
    
    def _save_cache(self):
        data = {
            "metadata": self.metadata,
            "types": self.types,
            "attributes": self.attributes,
            "relations": self.relations,
        }
        with open(self.CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    # =========================================================================
    # v3 NEW METHODS
    # =========================================================================
    
    def tty_to_entity_type(self, tty: str) -> str:
        """Convert RxNorm TTY to entity type name."""
        return TTY_TO_ENTITY_TYPE.get(tty, "DrugProduct")
    
    def get_relation_type_for_tty_pair(self, source_tty: str, target_tty: str, rela_code: str = None) -> Optional[str]:
        """Determine the semantic relation type from TTY pair and rela_code."""
        for rel_name, rel_def in RELATION_TYPE_DEFINITIONS.items():
            from_ttys = rel_def.get("from_tty")
            to_ttys = rel_def.get("to_tty")
            rel_codes = rel_def.get("rela_code", "")
            
            if from_ttys and to_ttys:
                if source_tty in from_ttys and target_tty in to_ttys:
                    if rela_code and rel_codes:
                        if rela_code in rel_codes.split(","):
                            return rel_name
                    else:
                        return rel_name
        return None
    
    # =========================================================================
    # CORE METHODS (backward compatible with v2)
    # =========================================================================
    
    def attr(self, name: str) -> str:
        if name in GRC20_IMPLICIT_ATTRIBUTES:
            return GRC20_IMPLICIT_ATTRIBUTES[name]
        if name in GRC20_RELATION_ATTRIBUTES:
            return GRC20_RELATION_ATTRIBUTES[name]
        if name not in self.attributes:
            raise KeyError(f"Unknown attribute: {name}")
        return self.attributes[name]
    
    def rel(self, name: str) -> str:
        if name not in self.relations:
            raise KeyError(f"Unknown relation: {name}")
        return self.relations[name]
    
    def type_id(self, name: str) -> str:
        if name not in self.types:
            raise KeyError(f"Unknown type: {name}")
        return self.types[name]
    
    def triple(self, entity_id: str, attribute: str, value: Any, value_type: str = None) -> dict:
        attr_id = self.attr(attribute)
        if value_type is None:
            value_type = ATTRIBUTES.get(attribute, {}).get("value_type", "TEXT")
        
        type_map = {"TEXT": 1, "NUMBER": 2, "CHECKBOX": 3, "URL": 4, "TIME": 5, "POINT": 6}
        grc_type = type_map.get(value_type.upper(), 1)
        
        return {
            "entity": entity_id,
            "attribute": attr_id,
            "value": {"type": grc_type, "value": str(value) if value is not None else ""},
        }
    
    def relation(self, from_entity: str, relation_type: str, to_entity: str, 
                 relation_id: Optional[str] = None,
                 rela_code: Optional[str] = None,
                 source_tty: Optional[str] = None,
                 target_tty: Optional[str] = None) -> List[dict]:
        """
        Create a relation entity with GRC-20 structure.
        
        v3 extension: Relations can have rela_code, source_tty, target_tty attributes.
        These are optional and backward compatible with v2 usage.
        """
        if relation_id is None:
            relation_id = generate_grc20_id()
        
        rel_type_id = self.rel(relation_type)
        relation_entity_type_id = self.type_id("Relation")
        
        triples = [
            {"entity": relation_id, "attribute": GRC20_SYSTEM_TYPES["Type"], 
             "value": {"type": 1, "value": relation_entity_type_id}},
            {"entity": relation_id, "attribute": GRC20_SYSTEM_TYPES["Type"], 
             "value": {"type": 1, "value": rel_type_id}},
            {"entity": relation_id, "attribute": GRC20_RELATION_ATTRIBUTES["from_entity"], 
             "value": {"type": 1, "value": from_entity}},
            {"entity": relation_id, "attribute": GRC20_RELATION_ATTRIBUTES["to_entity"], 
             "value": {"type": 1, "value": to_entity}},
        ]
        
        # v3: Add relation attributes for RxNorm relationships (optional)
        if rela_code:
            triples.append(self.triple(relation_id, "rela_code", rela_code))
        if source_tty:
            triples.append(self.triple(relation_id, "source_tty", source_tty))
        if target_tty:
            triples.append(self.triple(relation_id, "target_tty", target_tty))
        
        return triples
    
    def create_entity(self, entity_type: str, name: str, entity_id: Optional[str] = None,
                      rxcui: Optional[str] = None, tty: Optional[str] = None) -> dict:
        """
        Create an entity with GRC-20 structure.
        
        v3 extension: Optional rxcui and tty parameters for RxNorm entities.
        """
        if entity_id is None:
            entity_id = generate_grc20_id()
        
        type_id = self.types.get(entity_type)
        triples = []
        
        if type_id:
            triples.append({"entity": entity_id, "attribute": GRC20_SYSTEM_TYPES["Type"], 
                          "value": {"type": 1, "value": type_id}})
        
        triples.append(self.triple(entity_id, "name", name))
        
        # v3: Add RxNorm-specific attributes if provided
        if rxcui:
            triples.append(self.triple(entity_id, "rxcui", rxcui))
        
        if tty:
            triples.append(self.triple(entity_id, "tty", tty))
        
        return {"entity": entity_id, "triples": triples}
    
    def create_provenance(self, source: str, citation: str, date_accessed: str, 
                          source_url: str = None, provenance_type: str = "IMPORTED") -> dict:
        """Create a provenance entity."""
        entity_id = generate_grc20_id(seed=f"prov_{source}_{date_accessed}")
        type_id = self.types.get("Provenance")
        
        triples = [
            {"entity": entity_id, "attribute": GRC20_SYSTEM_TYPES["Type"], 
             "value": {"type": 1, "value": type_id}},
            self.triple(entity_id, "name", f"{source} - {date_accessed}"),
            self.triple(entity_id, "source", source),
            self.triple(entity_id, "citation", citation),
            self.triple(entity_id, "date_accessed", date_accessed),
        ]
        
        if source_url:
            triples.append(self.triple(entity_id, "source_url", source_url))
        
        triples.append(self.triple(entity_id, "provenance_type", provenance_type))
        
        return {"entity": entity_id, "triples": triples}
    
    def add_provenance_link(self, entity: dict, provenance_id: str) -> dict:
        """Add a provenance link to an entity."""
        entity_copy = {
            "entity": entity.get("entity"),
            "triples": entity.get("triples", []).copy()
        }
        
        entity_copy["triples"].append({
            "entity": entity_copy["entity"],
            "attribute": self.attr("provenance"),
            "value": {"type": 1, "value": provenance_id}
        })
        
        return entity_copy


if __name__ == "__main__":
    schema = PharmaSchema()
    print(f"\n{'='*60}")
    print(f"Pharma Schema v{schema.metadata.get('version', '?.?.?')}")
    print(f"{'='*60}")
    print(f"Types: {len(schema.types)}")
    print(f"Attributes: {len(schema.attributes)}")
    print(f"Relations: {len(schema.relations)}")
    
    # Test TTY mapping (v3 feature)
    print("\nTTY to Entity Type mapping:")
    for tty in ["IN", "PIN", "SCDC", "SCDF", "SCD", "SBD", "BN", "DF"]:
        entity_type = schema.tty_to_entity_type(tty)
        print(f"  {tty:8} -> {entity_type}")
    
    # Test relation type detection (v3 feature)
    print("\nRelation type detection (TTY pairs):")
    tests = [
        ("IN", "SCDC", "RO"),
        ("IN", "SCDF", "RO"),
        ("SCDC", "SCD", "RO"),
        ("SCD", "SBD", "RN"),
    ]
    for src, tgt, code in tests:
        rel = schema.get_relation_type_for_tty_pair(src, tgt, code)
        print(f"  {src} --[{code}]--> {tgt} = {rel}")
    
    # Test backward compatibility (v2 style calls)
    print("\nBackward compatibility test (v2 style):")
    entity = schema.create_entity("Ingredient", "Acetaminophen")
    print(f"  Created entity: {entity['entity'][:10]}...")
    
    rel = schema.relation(entity['entity'], "has_ingredient", "test-drug-id")
    print(f"  Created relation: {len(rel)} triples")
