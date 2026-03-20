#!/usr/bin/env python3
"""
Pharma Knowledge Graph Schema v4.0
==================================

GRC-20 compliant schema aligned with RxNorm TTY structure.

Key Changes from v3:
- Renamed "attribute" → "property" for GRC-20 terminology alignment
- Changed ID format from Base58 → UUID (RFC 4122, non-hyphenated)
- Added predefined provenance sources with runtime date fill
- Added CSV export for ontology (human review)
- Added JSONL export for data (SDK import)
"""

import json
import csv
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# =============================================================================
# GRC-20 STANDARD IDS (from spec - these are FIXED, non-hyphenated)
# =============================================================================

GRC20_STANDARD_PROPERTY_IDS = {
    "name": "a126ca530c8e48d5b88882c734c38935",
    "description": "9b1f76ff9711404c861e59dc3fa7d037",
}

# =============================================================================
# PREDEFINED PROVENANCE SOURCES
# =============================================================================

PROVENANCE_SOURCES = {
    "RxNorm": {
        "name": "RxNorm",
        "citation_template": "RxNorm [Internet]. Bethesda (MD): National Library of Medicine (US); [cited {date}]. Available from: https://rxnorm.nlm.nih.gov/",
        "source_url": "https://rxnorm.nlm.nih.gov/",
        "provenance_type": "IMPORTED",
    },
    "PubChem": {
        "name": "PubChem",
        "citation_template": "PubChem [Internet]. Bethesda (MD): National Library of Medicine (US); [cited {date}]. Available from: https://pubchem.ncbi.nlm.nih.gov/",
        "source_url": "https://pubchem.ncbi.nlm.nih.gov/",
        "provenance_type": "IMPORTED",
    },
    "DailyMed": {
        "name": "DailyMed",
        "citation_template": "DailyMed [Internet]. Bethesda (MD): National Library of Medicine (US); [cited {date}]. Available from: https://dailymed.nlm.nih.gov/",
        "source_url": "https://dailymed.nlm.nih.gov/",
        "provenance_type": "IMPORTED",
    },
}

# =============================================================================
# RXNORM TTY TO ENTITY TYPE MAPPING
# =============================================================================

TTY_TO_ENTITY_TYPE = {
    "IN":   "Ingredient",
    "PIN":  "PreciseIngredient",
    "MIN":  "MultipleIngredient",
    "SU":   "SpecificSubstance",
    "SCDC": "ClinicalDrugComponent",
    "SCDF": "ClinicalDrugForm",
    "SCDG": "ClinicalDrugGroup",
    "SCDGP":"ClinicalDrugGroupPrecise",
    "SCD":  "ClinicalDrug",
    "SBDC": "BrandedDrugComponent",
    "SBDF": "BrandedDrugForm",
    "SBDG": "BrandedDrugGroup",
    "SBD":  "BrandedDrug",
    "BN":   "BrandName",
    "DF":   "DoseForm",
    "DFG":  "DoseFormGroup",
    "GPCK": "GenericPack",
    "BPCK": "BrandPack",
    "PSN":  "PrescribableName",
    "SY":   "Synonym",
    "TMSY": "TallManSynonym",
    "DP":   "DrugProduct",
    "MTH_RXN_DP": "MTHDrugProduct",
}

# =============================================================================
# ENTITY TYPE DEFINITIONS
# =============================================================================

ENTITY_TYPES = {
    # RxNorm TTY-based types
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
    
    # Non-RxNorm types
    "PackageInsert": {"description": "FDA drug label/package insert document", "tty": None},
    "Manufacturer": {"description": "Drug manufacturer or labeler company", "tty": None},
    "NDC": {"description": "National Drug Code identifier", "tty": None},
    "Provenance": {"description": "Data source provenance", "tty": None},
    "Section": {"description": "Document section (e.g., drug label section)", "tty": None},
    "DrugClass": {"description": "Drug classification or category", "tty": None},
    "Relation": {"description": "GRC-20 relation entity (edge between nodes)", "tty": None},
    "PubChemCompound": {"description": "PubChem chemical compound entry", "tty": None},
}

# =============================================================================
# PROPERTY DEFINITIONS (renamed from ATTRIBUTES)
# =============================================================================

PROPERTIES = {
    # Core properties
    "name": {"value_type": "TEXT", "description": "Primary name or label"},
    "description": {"value_type": "TEXT", "description": "Description or summary text"},
    "rxcui": {"value_type": "TEXT", "description": "RxNorm Concept Unique Identifier"},
    "tty": {"value_type": "TEXT", "description": "RxNorm Term Type"},
    
    # Relation properties
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
    
    # DailyMed / Package Insert properties
    "ndc_code": {"value_type": "TEXT", "description": "National Drug Code"},
    "fda_set_id": {"value_type": "TEXT", "description": "FDA SET ID for package insert"},
    "effective_time": {"value_type": "TIME", "description": "Effective date/time of drug label"},
    "content": {"value_type": "TEXT", "description": "Text content of a document section"},
    "set_id": {"value_type": "TEXT", "description": "Unique identifier for document set"},
    
    # PubChem properties
    "pubchem_date": {"value_type": "TIME", "description": "PubChem data retrieval date"},
    "pmid": {"value_type": "TEXT", "description": "PubMed ID reference"},
    "sid": {"value_type": "TEXT", "description": "PubChem Substance ID"},
    "mesh_classes": {"value_type": "TEXT", "description": "MeSH classification codes"},
    
    # Provenance properties
    "source": {"value_type": "TEXT", "description": "Data source name"},
    "citation": {"value_type": "TEXT", "description": "Citation for data source"},
    "date_accessed": {"value_type": "TIME", "description": "Date data was accessed"},
    "source_url": {"value_type": "URL", "description": "URL to data source"},
    "provenance_type": {"value_type": "TEXT", "description": "Type of provenance: AUTOMATED, EXPERT, INFERRED, IMPORTED"},
    
    # Section properties
    "section_type": {"value_type": "TEXT", "description": "Type of document section"},
    "sequence": {"value_type": "NUMBER", "description": "Order sequence"},
    
    # Drug classification
    "class_name": {"value_type": "TEXT", "description": "Drug class name"},
    "class_type": {"value_type": "TEXT", "description": "Classification system (ATC, MeSH, etc.)"},
    "class_code": {"value_type": "TEXT", "description": "Classification code"},
    
    # Clinical properties
    "clinical_weight": {"value_type": "NUMBER", "description": "Weighted clinical relationship"},
    "evidence": {"value_type": "TEXT", "description": "Evidence supporting a clinical relationship"},
}

# =============================================================================
# RELATION TYPE DEFINITIONS
# =============================================================================

RELATION_TYPES = {
    # Document structure
    "has_section": {"description": "Package insert has this section", "inverse": "section_of"},
    "section_of": {"description": "Section belongs to this package insert", "inverse": "has_section"},
    "manufactured_by": {"description": "Package insert manufactured by this company", "inverse": "manufactures"},
    "manufactures": {"description": "Manufacturer produces this drug product", "inverse": "manufactured_by"},
    
    # Ingredient relationships
    "has_ingredient": {"description": "Drug has this ingredient", "inverse": "ingredient_of"},
    "ingredient_of": {"description": "Ingredient is in this drug", "inverse": "has_ingredient"},
    "has_precise_ingredient": {"description": "Drug has this precise ingredient (salt form)", "inverse": "precise_ingredient_of"},
    "precise_ingredient_of": {"description": "Precise ingredient is in this drug", "inverse": "has_precise_ingredient"},
    "has_ingredients": {"description": "Multiple ingredients drug has", "inverse": "ingredients_of"},
    "ingredients_of": {"description": "Ingredients are in this multiple ingredient drug", "inverse": "has_ingredients"},
    
    # Dose form relationships
    "has_dose_form": {"description": "Drug has this dose form", "inverse": "dose_form_of"},
    "dose_form_of": {"description": "Dose form is used by this drug", "inverse": "has_dose_form"},
    "has_doseformgroup": {"description": "Drug belongs to this dose form group", "inverse": "doseformgroup_of"},
    "doseformgroup_of": {"description": "Dose form group contains this drug", "inverse": "has_doseformgroup"},
    
    # Brand relationships
    "has_tradename": {"description": "Drug has this brand/trade name", "inverse": "tradename_of"},
    "tradename_of": {"description": "Brand name is for this drug", "inverse": "has_tradename"},
    
    # Taxonomy relationships
    "is_a": {"description": "Entity is a subtype of", "inverse": "inverse_isa"},
    "inverse_isa": {"description": "Entity is a supertype of", "inverse": "is_a"},
    
    # Component relationships
    "consists_of": {"description": "Drug consists of these components", "inverse": "constitutes"},
    "constitutes": {"description": "Component constitutes this drug", "inverse": "consists_of"},
    "contains": {"description": "Pack contains this drug", "inverse": "contained_in"},
    "contained_in": {"description": "Drug is contained in this pack", "inverse": "contains"},
    "has_part": {"description": "Entity has this part", "inverse": "part_of"},
    "part_of": {"description": "Entity is part of this", "inverse": "has_part"},
    
    # Form relationships
    "has_form": {"description": "Drug has this form (salt form)", "inverse": "form_of"},
    "form_of": {"description": "Form is of this drug", "inverse": "has_form"},
    "reformulated_to": {"description": "Drug was reformulated to this", "inverse": "reformulation_of"},
    "reformulation_of": {"description": "Drug is a reformulation of this", "inverse": "reformulated_to"},
    "has_quantified_form": {"description": "Drug has this quantified form", "inverse": "quantified_form_of"},
    "quantified_form_of": {"description": "Quantified form is of this drug", "inverse": "has_quantified_form"},
    
    # Boss relationships
    "has_boss": {"description": "Drug has this boss (active moiety)", "inverse": "boss_of"},
    "boss_of": {"description": "Boss (active moiety) of this drug", "inverse": "has_boss"},
    
    # Equivalence
    "equivalent_to": {"description": "Entity is equivalent to", "inverse": "equivalent_to"},
    
    # NDC mapping
    "maps_to_rxcui": {"description": "NDC maps to this RxCUI", "inverse": "mapped_from_ndc"},
    "mapped_from_ndc": {"description": "RxCUI is mapped from this NDC", "inverse": "maps_to_rxcui"},
    
    # Provenance
    "has_provenance": {"description": "Entity has provenance information", "inverse": None},
    
    # PubChem
    "has_pubchem": {"description": "Entity links to PubChem compound", "inverse": None},
    
    # TTY-based relationships
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


def generate_uuid(seed: str = None) -> str:
    """Generate a valid RFC 4122 UUID without hyphens (GRC-20 recommended format).
    
    Args:
        seed: Optional seed string for deterministic UUID generation.
              Same seed always produces same UUID.
    
    Returns:
        UUID string in format: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (32 hex chars)
    """
    if seed:
        # Use UUID5 for deterministic generation from seed
        namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
        return str(uuid.uuid5(namespace, seed)).replace('-', '')
    else:
        return str(uuid.uuid4()).replace('-', '')


class PharmaSchema:
    """Pharma Knowledge Graph Schema v4 - GRC-20 Aligned with RxNorm TTY."""
    
    CACHE_FILE = Path(__file__).parent / "schema_cache.json"
    
    def __init__(self):
        self.types: Dict[str, str] = {}
        self.properties: Dict[str, str] = {}  # Renamed from attributes
        self.relations: Dict[str, str] = {}
        self.metadata: Dict[str, Any] = {}
        self.provenance_entities: Dict[str, str] = {}  # source_name -> entity_id
        
        if not self._load_cache():
            self._generate_ids()
            self._create_provenance_entities()
            self._save_cache()
    
    def _load_cache(self) -> bool:
        """Load schema from cache if available."""
        if not self.CACHE_FILE.exists():
            print("[INFO] No cache found. Generating new schema...")
            return False
        try:
            with open(self.CACHE_FILE, 'r') as f:
                data = json.load(f)
            self.types = data.get("types", {})
            self.properties = data.get("properties", {})
            self.relations = data.get("relations", {})
            self.metadata = data.get("metadata", {})
            self.provenance_entities = data.get("provenance_entities", {})
            print(f"[INFO] Loaded schema from cache: {len(self.types)} types, {len(self.properties)} properties, {len(self.relations)} relations")
            return True
        except Exception as e:
            print(f"[WARN] Cache load failed: {e}. Regenerating...")
            return False
    
    def _generate_ids(self):
        """Generate UUIDs for all schema elements."""
        self.metadata = {
            "version": "4.0.0",
            "created": datetime.now().isoformat(),
            "description": "Pharma Knowledge Graph Schema v4 - UUID-based, Property terminology",
        }
        
        # Generate type IDs
        for type_name in ENTITY_TYPES:
            self.types[type_name] = generate_uuid(seed=f"pharma_v4_type_{type_name}")
        
        # Generate property IDs (use fixed IDs for standard properties)
        for prop_name in PROPERTIES:
            if prop_name in GRC20_STANDARD_PROPERTY_IDS:
                self.properties[prop_name] = GRC20_STANDARD_PROPERTY_IDS[prop_name]
            else:
                self.properties[prop_name] = generate_uuid(seed=f"pharma_v4_prop_{prop_name}")
        
        # Generate relation type IDs
        for rel_name in RELATION_TYPES:
            self.relations[rel_name] = generate_uuid(seed=f"pharma_v4_rel_{rel_name}")
        
        print(f"[INFO] Generated {len(self.types)} types, {len(self.properties)} properties, {len(self.relations)} relations")
    
    def _create_provenance_entities(self):
        """Create provenance entity IDs for each source."""
        for source_name in PROVENANCE_SOURCES:
            self.provenance_entities[source_name] = generate_uuid(seed=f"pharma_v4_prov_{source_name}")
    
    def _save_cache(self):
        """Save schema to cache."""
        data = {
            "metadata": self.metadata,
            "types": self.types,
            "properties": self.properties,
            "relations": self.relations,
            "provenance_entities": self.provenance_entities,
        }
        with open(self.CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[INFO] Schema cached to {self.CACHE_FILE}")
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def tty_to_entity_type(self, tty: str) -> str:
        """Convert RxNorm TTY to entity type name."""
        return TTY_TO_ENTITY_TYPE.get(tty, "DrugProduct")
    
    def prop(self, name: str) -> str:
        """Get property ID by name."""
        if name in GRC20_STANDARD_PROPERTY_IDS:
            return GRC20_STANDARD_PROPERTY_IDS[name]
        if name not in self.properties:
            raise KeyError(f"Unknown property: {name}")
        return self.properties[name]
    
    def rel(self, name: str) -> str:
        """Get relation type ID by name."""
        if name not in self.relations:
            raise KeyError(f"Unknown relation: {name}")
        return self.relations[name]
    
    def type_id(self, name: str) -> str:
        """Get entity type ID by name."""
        if name not in self.types:
            raise KeyError(f"Unknown type: {name}")
        return self.types[name]
    
    # =========================================================================
    # ENTITY CREATION METHODS
    # =========================================================================
    
    def create_entity(self, entity_type: str, name: str, entity_id: Optional[str] = None,
                      rxcui: Optional[str] = None, tty: Optional[str] = None) -> dict:
        """Create an entity with GRC-20 structure.
        
        Returns:
            dict with 'id', 'name', 'types', 'values' for Geo SDK import
        """
        if entity_id is None:
            entity_id = generate_uuid()
        
        entity = {
            "id": entity_id,
            "name": name,  # Keep at top level for convenience
            "types": [self.type_id(entity_type)],
            "values": [
                {"property": self.prop("name"), "value": name}  # GRC-20 compliant
            ]
        }
        
        # Add RxNorm-specific properties if provided
        if rxcui:
            entity["values"].append({
                "property": self.prop("rxcui"),
                "value": rxcui
            })
        
        if tty:
            entity["values"].append({
                "property": self.prop("tty"),
                "value": tty
            })
        
        return entity
    
    def add_property(self, entity: dict, property_name: str, value: Any) -> dict:
        """Add a property value to an entity.
        
        Returns:
            Modified entity dict
        """
        entity["values"].append({
            "property": self.prop(property_name),
            "value": value
        })
        return entity
    
    # =========================================================================
    # RELATION CREATION METHODS
    # =========================================================================
    
    def create_relation(self, from_entity_id: str, relation_type: str, to_entity_id: str,
                        relation_id: Optional[str] = None,
                        rela_code: Optional[str] = None,
                        source_tty: Optional[str] = None,
                        target_tty: Optional[str] = None) -> dict:
        """Create a relation with GRC-20 structure.
        
        Returns:
            dict with 'id', 'type', 'from', 'to', 'values' for Geo SDK import
        """
        if relation_id is None:
            relation_id = generate_uuid()
        
        relation = {
            "id": relation_id,
            "type": self.rel(relation_type),
            "from": from_entity_id,
            "to": to_entity_id,
            "values": []
        }
        
        # Add relation attributes
        if rela_code:
            relation["values"].append({
                "property": self.prop("rela_code"),
                "value": rela_code
            })
        
        if source_tty:
            relation["values"].append({
                "property": self.prop("source_tty"),
                "value": source_tty
            })
        
        if target_tty:
            relation["values"].append({
                "property": self.prop("target_tty"),
                "value": target_tty
            })
        
        return relation
    
    # =========================================================================
    # PROVENANCE METHODS
    # =========================================================================
    
    def create_provenance_entity(self, source_name: str, date_accessed: str = None) -> dict:
        """Create a provenance entity for a data source.
        
        Args:
            source_name: One of the keys in PROVENANCE_SOURCES
            date_accessed: Date string (default: today)
        
        Returns:
            Entity dict for Geo SDK import
        """
        if source_name not in PROVENANCE_SOURCES:
            raise ValueError(f"Unknown provenance source: {source_name}")
        
        if date_accessed is None:
            date_accessed = datetime.now().strftime("%Y-%m-%d")
        
        source = PROVENANCE_SOURCES[source_name]
        citation = source["citation_template"].format(date=date_accessed)
        
        entity = {
            "id": self.provenance_entities[source_name],
            "name": source["name"],
            "types": [self.type_id("Provenance")],
            "values": [
                {"property": self.prop("name"), "value": source["name"]},  # GRC-20 name
                {"property": self.prop("citation"), "value": citation},
                {"property": self.prop("date_accessed"), "value": date_accessed},
                {"property": self.prop("source_url"), "value": source["source_url"]},
                {"property": self.prop("provenance_type"), "value": source["provenance_type"]},
            ]
        }
        
        return entity
    
    def add_provenance_relation(self, entity_id: str, source_name: str) -> dict:
        """Create a has_provenance relation from entity to source.
        
        Args:
            entity_id: The entity to link
            source_name: One of the keys in PROVENANCE_SOURCES
        
        Returns:
            Relation dict for Geo SDK import
        """
        if source_name not in PROVENANCE_SOURCES:
            raise ValueError(f"Unknown provenance source: {source_name}")
        
        return self.create_relation(
            from_entity_id=entity_id,
            relation_type="has_provenance",
            to_entity_id=self.provenance_entities[source_name]
        )
    
    # =========================================================================
    # EXPORT METHODS
    # =========================================================================
    
    def export_ontology_csv(self, output_dir: Path):
        """Export ontology as CSV files for human review (Geo devs).
        
        Creates:
            - types.csv
            - properties.csv  
            - relation_types.csv
            - provenance_sources.csv
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export types
        with open(output_dir / "types.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'description', 'tty'])
            for name, type_id in self.types.items():
                info = ENTITY_TYPES.get(name, {})
                writer.writerow([
                    type_id,
                    name,
                    info.get('description', ''),
                    info.get('tty', '')
                ])
        
        # Export properties
        with open(output_dir / "properties.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'value_type', 'description'])
            for name, prop_id in self.properties.items():
                info = PROPERTIES.get(name, {})
                writer.writerow([
                    prop_id,
                    name,
                    info.get('value_type', 'TEXT'),
                    info.get('description', '')
                ])
        
        # Export relation types
        with open(output_dir / "relation_types.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'description', 'inverse'])
            for name, rel_id in self.relations.items():
                info = RELATION_TYPES.get(name, {})
                writer.writerow([
                    rel_id,
                    name,
                    info.get('description', ''),
                    info.get('inverse', '')
                ])
        
        # Export provenance sources
        with open(output_dir / "provenance_sources.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'citation_template', 'source_url', 'provenance_type'])
            for source_name, source_id in self.provenance_entities.items():
                info = PROVENANCE_SOURCES[source_name]
                writer.writerow([
                    source_id,
                    source_name,
                    info['citation_template'],
                    info['source_url'],
                    info['provenance_type']
                ])
        
        print(f"[INFO] Ontology exported to {output_dir}/")
        print(f"  - types.csv: {len(self.types)} types")
        print(f"  - properties.csv: {len(self.properties)} properties")
        print(f"  - relation_types.csv: {len(self.relations)} relation types")
        print(f"  - provenance_sources.csv: {len(PROVENANCE_SOURCES)} sources")
    
    def export_data_jsonl(self, entities: List[dict], relations: List[dict], 
                          output_dir: Path, include_provenance: bool = True):
        """Export entities and relations to JSONL files for Geo SDK import.
        
        Args:
            entities: List of entity dicts
            relations: List of relation dicts
            output_dir: Output directory
            include_provenance: Whether to include provenance entities
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export provenance entities
        if include_provenance:
            with open(output_dir / "provenance.jsonl", 'w', encoding='utf-8') as f:
                for source_name in PROVENANCE_SOURCES:
                    prov = self.create_provenance_entity(source_name)
                    f.write(json.dumps(prov) + '\n')
        
        # Export entities
        with open(output_dir / "entities.jsonl", 'w', encoding='utf-8') as f:
            for entity in entities:
                f.write(json.dumps(entity) + '\n')
        
        # Export relations
        with open(output_dir / 'relations.jsonl', 'w', encoding='utf-8') as f:
            for relation in relations:
                f.write(json.dumps(relation) + '\n')
        
        print(f"[INFO] Data exported to {output_dir}/")
        print(f"  - provenance.jsonl: {len(PROVENANCE_SOURCES) if include_provenance else 0} sources")
        print(f"  - entities.jsonl: {len(entities)} entities")
        print(f"  - relations.jsonl: {len(relations)} relations")
    
    def export_schema_json(self, output_path: Path):
        """Export complete schema as a single JSON file.
        
        Args:
            output_path: Output file path
        """
        # Build types list
        types_list = []
        for name, type_id in self.types.items():
            info = ENTITY_TYPES.get(name, {})
            types_list.append({
                "id": type_id,
                "name": name,
                "description": info.get("description", ""),
                "tty": info.get("tty"),
            })
        
        # Build properties list
        properties_list = []
        for name, prop_id in self.properties.items():
            info = PROPERTIES.get(name, {})
            properties_list.append({
                "id": prop_id,
                "name": name,
                "value_type": info.get("value_type", "TEXT"),
                "description": info.get("description", ""),
            })
        
        # Build relations list
        relations_list = []
        for name, rel_id in self.relations.items():
            info = RELATION_TYPES.get(name, {})
            relations_list.append({
                "id": rel_id,
                "name": name,
                "description": info.get("description", ""),
                "inverse": info.get("inverse"),
            })
        
        # Build provenance list
        provenance_list = []
        for source_name, source_id in self.provenance_entities.items():
            info = PROVENANCE_SOURCES[source_name]
            provenance_list.append({
                "id": source_id,
                "name": source_name,
                "citation_template": info["citation_template"],
                "source_url": info["source_url"],
                "provenance_type": info["provenance_type"],
            })
        
        schema = {
            "metadata": self.metadata,
            "types": types_list,
            "properties": properties_list,
            "relations": relations_list,
            "provenance_sources": provenance_list,
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2)
        
        print(f"[INFO] Schema exported to {output_path}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pharma Knowledge Graph Schema v4")
    parser.add_argument("--export-ontology", type=str, help="Export ontology CSVs to directory")
    parser.add_argument("--export-schema", type=str, help="Export schema JSON to file")
    parser.add_argument("--clear-cache", action="store_true", help="Clear schema cache and regenerate")
    args = parser.parse_args()
    
    # Clear cache if requested
    if args.clear_cache:
        cache_file = Path(__file__).parent / "schema_cache.json"
        if cache_file.exists():
            cache_file.unlink()
            print(f"[INFO] Cache cleared: {cache_file}")
    
    # Initialize schema
    schema = PharmaSchema()
    
    print(f"\n{'='*60}")
    print(f"Pharma Schema v{schema.metadata.get('version', '?.?.?')}")
    print(f"{'='*60}")
    print(f"Types: {len(schema.types)}")
    print(f"Properties: {len(schema.properties)}")
    print(f"Relations: {len(schema.relations)}")
    print(f"Provenance Sources: {len(schema.provenance_entities)}")
    
    # Show provenance entities
    print("\nProvenance Entities:")
    for source_name, entity_id in schema.provenance_entities.items():
        print(f"  {source_name}: {entity_id}")
    
    # Export ontology if requested
    if args.export_ontology:
        schema.export_ontology_csv(Path(args.export_ontology))
    
    # Export schema if requested
    if args.export_schema:
        schema.export_schema_json(Path(args.export_schema))
    
    # Test entity creation
    print("\nTest entity creation:")
    entity = schema.create_entity("Ingredient", "Acetaminophen", rxcui="161", tty="IN")
    entity = schema.add_property(entity, "smiles", "CC(=O)NC1=CC=C(C=C1)O")
    entity = schema.add_property(entity, "inchikey", "RZVAJINKPMORJF-UHFFFAOYSA-N")
    print(f"  Entity ID: {entity['id']}")
    print(f"  Name: {entity['name']}")
    print(f"  Types: {entity['types']}")
    print(f"  Values: {len(entity['values'])}")
    
    # Test relation creation
    print("\nTest relation creation:")
    relation = schema.create_relation(
        from_entity_id="test-drug-id",
        relation_type="has_ingredient",
        to_entity_id=entity['id'],
        rela_code="RO",
        source_tty="SCD",
        target_tty="IN"
    )
    print(f"  Relation ID: {relation['id']}")
    print(f"  Type: {relation['type']}")
    print(f"  From → To: {relation['from'][:8]}... → {relation['to'][:8]}...")
    
    # Test provenance
    print("\nTest provenance:")
    prov = schema.create_provenance_entity("RxNorm")
    print(f"  RxNorm provenance: {prov['id']}")
    citation = [v for v in prov['values'] if v['property'] == schema.prop('citation')][0]
    print(f"  Citation: {citation['value'][:60]}...")
