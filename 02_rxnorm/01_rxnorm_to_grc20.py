#!/usr/bin/env python3
"""
RxNorm to GRC-20 Converter
==========================

Converts RxNorm data (RXNCONSO.RRF, RXNREL.RRF) to GRC-20 format.

ENTITY TYPES:
- RxNormConcept: RxCUI entities with TTY classification
- Ingredient: Active ingredients (IN, PIN)
- ClinicalDrug: Semantic clinical drugs (SCD)
- BrandedDrug: Semantic branded drugs (SBD)
- DoseForm: Dose forms (DF)

RELATIONSHIPS:
- HAS_INGREDIENT: Drug → Ingredient
- HAS_DOSE_FORM: Drug → DoseForm
- HAS_BRAND: ClinicalDrug → BrandName
- IS_SYNONYM: Concept → PreferredTerm
- SIMILAR_INGREDIENT: Ingredient → Ingredient

CREATED: 2026-02-22
"""

import json
import os
import sys
import zipfile
import hashlib
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple
import uuid
import base58

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
EXTRACTED_DIR = f"{RAW_DATA_DIR}/extracted_rrf"
OUTPUT_DIR = f"{BASE_DIR}/data/import_csvs"

# GRC-20 Standard Attributes (matching our NDC tether export)
GRC20_ATTRIBUTES = {
    "name": "LuBWqZAu6pz54eiJS5mLv8",
    "type": "Jfmby78N4BCseZinBmdVov",
    "description": "LA1DqP5v6QAdsgLPXGF3YA",
    # RxNorm-specific attributes
    "rxcui": "RxCui12345678901234IJ",
    "tty": "TtyCode123456789012AB",
    "primary_tty": "PrimaryTty12345678CD",
    "tier": "Tier1234567890123456EF",
    "all_ttys": "AllTtys12345678901234GH",
    "provenance_rxnorm": "ProvRxNorm12345678IJ",
    "rxnorm_hierarchy_level": "RxNormLevel12345678KL",
    # RxNorm relationships
    "has_ingredient": "HasIngredient123456MN",
    "has_dose_form": "HasDoseForm12345678OP",
    "has_brand": "HasBrand1234567890QR",
    "is_synonym": "IsSynonym1234567890ST",
    "similar_ingredient": "SimilarIngredientUV",
    "maps_to_rxcui": "MapsToRxcui12345678WX",
}

# RxNorm TTY definitions
PRIMARY_TTYS = {
    'IN', 'PIN', 'MIN', 'SCDC', 'SCDF', 'SCDFP', 'SCDG', 'SCDGP', 'SCD', 
    'SBDC', 'SBDF', 'SBDFP', 'SBDG', 'SBD', 'BN', 'DF', 'DFG', 'GPCK', 'BPCK'
}

SYNONYM_TTYS = {'SY', 'PSN', 'TMSY'}

TTY_DESCRIPTIONS = {
    'IN': 'Ingredient',
    'PIN': 'Precise Ingredient',
    'MIN': 'Multiple Ingredient',
    'SCDC': 'Semantic Clinical Drug Component',
    'SCDF': 'Semantic Clinical Drug Form',
    'SCDFP': 'Semantic Clinical Drug Form Pack',
    'SCDG': 'Semantic Clinical Drug Group',
    'SCDGP': 'Semantic Clinical Drug Group Pack',
    'SCD': 'Semantic Clinical Drug',
    'SBDC': 'Semantic Branded Drug Component',
    'SBDF': 'Semantic Branded Drug Form',
    'SBDFP': 'Semantic Branded Drug Form Pack',
    'SBDG': 'Semantic Branded Drug Group',
    'SBD': 'Semantic Branded Drug',
    'BN': 'Brand Name',
    'DF': 'Dose Form',
    'DFG': 'Dose Form Group',
    'GPCK': 'Generic Pack',
    'BPCK': 'Brand Pack',
    'PSN': 'Prescribable Name',
    'SY': 'Synonym',
    'TMSY': 'Typed Synonym'
}

RXNORM_HIERARCHY = {
    "Molecular/Chemical Level": {'PIN': 'Precise Ingredient', 'IN': 'Ingredient'},
    "Component Level": {'SCDC': 'Semantic Clinical Drug Component', 'SBDC': 'Semantic Branded Drug Component'},
    "Complete Drug Level": {'SCD': 'Semantic Clinical Drug', 'SBD': 'Semantic Branded Drug'},
    "Form/Packaging Level": {'DF': 'Dose Form', 'GPCK': 'Generic Pack', 'BPCK': 'Brand Pack'},
    "Naming/Synonym Level": {'PSN': 'Prescribable Name', 'SY': 'Synonym'}
}

# =============================================================================
# UTILITIES
# =============================================================================

def generate_grc20_id() -> str:
    return base58.b58encode(uuid.uuid4().bytes).decode()[:22].ljust(22, '1')[:22]


def create_triple(entity_id: str, attr_name: str, value: any, value_type: str = "TEXT") -> dict:
    attr_id = GRC20_ATTRIBUTES.get(attr_name, generate_grc20_id())
    if isinstance(value, bool):
        value_type = "CHECKBOX"
        value = str(value).lower()
    elif isinstance(value, list):
        value = json.dumps(value)
    return {"entity": entity_id, "attribute": attr_id, "value": {"type": 1 if value_type == "TEXT" else 3, "value": str(value)}}


def create_relation(entity_id: str, attr_name: str, target_id: str) -> dict:
    return {"entity": entity_id, "attribute": GRC20_ATTRIBUTES.get(attr_name, generate_grc20_id()), "value": {"type": 1, "value": target_id}}


def get_node_tier(primary_tty: str) -> str:
    tier_map = {
        'PIN': 'PreciseIngredient', 'IN': 'Ingredient',
        'SCDC': 'ClinicalComponent', 'SBDC': 'BrandedComponent',
        'SCD': 'ClinicalDrug', 'SBD': 'BrandedDrug',
        'DF': 'DoseForm', 'GPCK': 'GenericPack', 'BPCK': 'BrandPack',
        'BN': 'BrandName', 'PSN': 'PrescribableName', 'SY': 'Synonym',
        'MIN': 'MultiIngredient',
        'SCDG': 'ClinicalDrug', 'SBDG': 'ClinicalDrug',
        'SCDF': 'ClinicalComponent', 'SCDFP': 'ClinicalComponent',
        'SBDF': 'BrandedComponent', 'SBDFP': 'BrandedComponent',
        'SCDGP': 'ClinicalDrug', 'DFG': 'DoseForm',
    }
    return tier_map.get(primary_tty, 'Other')


def get_rxnorm_hierarchy_level(primary_tty: str) -> Tuple[Optional[str], Optional[str]]:
    for level, tty_dict in RXNORM_HIERARCHY.items():
        if primary_tty in tty_dict:
            return level, tty_dict[primary_tty]
    return None, None


def determine_primary_tty(ttys: Set[str]) -> Optional[str]:
    primary_ttys = [tty for tty in ttys if tty in PRIMARY_TTYS]
    if not primary_ttys:
        return list(ttys)[0] if ttys else None
    
    priority_order = ['SCD', 'SBD', 'MIN', 'IN', 'PIN', 'BN', 'SCDC', 'SBDC', 'DF', 'GPCK', 'BPCK']
    for tty in priority_order:
        if tty in primary_ttys:
            return tty
    return primary_ttys[0]


def create_provenance_hash(rxcui: str, source: str = "rxnorm", **kwargs) -> str:
    metadata = {"rxcui": rxcui, "source": source, "timestamp": datetime.now().isoformat(), **kwargs}
    return hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:16]


# =============================================================================
# RXNORM PARSER
# =============================================================================

class RxNormGRC20Converter:
    def __init__(self):
        self.concepts: Dict[str, dict] = {}
        self.relationships: List[dict] = []
        self.entities: List[dict] = []
        self.entity_index: Dict[str, int] = {}
        self.rxcui_to_entity: Dict[str, str] = {}
        self.tty_stats: Dict[str, int] = defaultdict(int)
        self.rel_stats: Dict[str, int] = defaultdict(int)
        self.selected_zip: Optional[str] = None
        
    def find_rxnorm_files(self) -> List[str]:
        """Find available RxNorm zip files"""
        zip_files = []
        for file in os.listdir(RAW_DATA_DIR):
            if file.startswith("RxNorm") and file.endswith(".zip"):
                zip_files.append(file)
        return sorted(zip_files, reverse=True)
    
    def extract_rxnorm(self, zip_file: str) -> str:
        """Extract RxNorm zip if needed"""
        extract_dir = os.path.join(EXTRACTED_DIR, zip_file.replace(".zip", "_extracted"))
        
        if os.path.exists(extract_dir):
            return extract_dir
        
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(os.path.join(RAW_DATA_DIR, zip_file), 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        return extract_dir
    
    def find_rrf_file(self, extract_dir: str, filename: str) -> Optional[str]:
        """Find a specific RRF file in extracted directory"""
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file == filename:
                    return os.path.join(root, file)
        return None
    
    def parse_concepts(self, conso_file: str) -> None:
        """Parse RXNCONSO.RRF to extract concepts"""
        print(f"  Parsing concepts from {os.path.basename(conso_file)}...")
        
        with open(conso_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 50000 == 0:
                    print(f"    Line {line_num:,}...")
                
                fields = line.strip().split('|')
                if len(fields) < 18:
                    continue
                
                rxcui = fields[0]
                name = fields[14]
                tty = fields[12]
                
                if not rxcui or not name or not tty:
                    continue
                
                self.tty_stats[tty] += 1
                
                if rxcui not in self.concepts:
                    self.concepts[rxcui] = {
                        'name': name,
                        'ttys': set(),
                        'tty_details': {},
                        'tty_names': {},
                    }
                
                self.concepts[rxcui]['ttys'].add(tty)
                self.concepts[rxcui]['tty_details'][tty] = self.concepts[rxcui]['tty_details'].get(tty, 0) + 1
                self.concepts[rxcui]['tty_names'][tty] = name
        
        print(f"  ✅ Parsed {len(self.concepts):,} unique RxCUIs")
    
    def parse_relationships(self, rel_file: str) -> None:
        """Parse RXNREL.RRF to extract relationships"""
        print(f"  Parsing relationships from {os.path.basename(rel_file)}...")
        
        with open(rel_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 100000 == 0:
                    print(f"    Line {line_num:,}...")
                
                fields = line.strip().split('|')
                if len(fields) < 9:
                    continue
                
                source_rxcui = fields[0]
                target_rxcui = fields[4]
                relationship = fields[7]
                
                if not source_rxcui or not target_rxcui or not relationship:
                    continue
                
                if source_rxcui not in self.concepts or target_rxcui not in self.concepts:
                    continue
                
                self.relationships.append({
                    'source': source_rxcui,
                    'target': target_rxcui,
                    'relationship': relationship,
                })
                self.rel_stats[relationship] += 1
        
        print(f"  ✅ Parsed {len(self.relationships):,} relationships")
    
    def enhance_connectivity(self) -> None:
        """Add enhanced relationships based on ingredient similarity"""
        print("  Enhancing connectivity...")
        
        ingredient_groups = defaultdict(list)
        for rxcui, data in self.concepts.items():
            if 'IN' in data['ttys']:
                first_word = data['name'].split()[0].lower()
                ingredient_groups[first_word].append(rxcui)
        
        enhanced = 0
        for first_word, rxcuis in ingredient_groups.items():
            if len(rxcuis) > 1:
                for i in range(len(rxcuis)):
                    for j in range(i + 1, min(len(rxcuis), 10)):  # Limit to prevent explosion
                        self.relationships.append({
                            'source': rxcuis[i],
                            'target': rxcuis[j],
                            'relationship': 'SIMILAR_INGREDIENT',
                        })
                        enhanced += 1
        
        print(f"  ✅ Added {enhanced:,} enhanced relationships")
    
    def convert_to_grc20(self) -> None:
        """Convert parsed data to GRC-20 format"""
        print("\n[3/5] Converting to GRC-20 format...")
        
        # Create type entities
        type_entities = {
            'RxNormConcept': generate_grc20_id(),
            'Ingredient': generate_grc20_id(),
            'ClinicalDrug': generate_grc20_id(),
            'BrandedDrug': generate_grc20_id(),
            'BrandName': generate_grc20_id(),
            'DoseForm': generate_grc20_id(),
        }
        
        for type_name, type_id in type_entities.items():
            self.entity_index[type_id] = len(self.entities)
            self.entities.append({
                "space": "rxnorm",
                "entity": type_id,
                "triples": [
                    create_triple(type_id, "name", type_name),
                    create_triple(type_id, "type", "type"),
                ]
            })
        
        print(f"  Created {len(type_entities)} type entities")
        
        # Create concept entities
        print(f"  Creating {len(self.concepts):,} concept entities...")
        
        for i, (rxcui, data) in enumerate(self.concepts.items()):
            primary_tty = determine_primary_tty(data['ttys'])
            tier = get_node_tier(primary_tty)
            hierarchy_level, hierarchy_desc = get_rxnorm_hierarchy_level(primary_tty)
            prov_hash = create_provenance_hash(rxcui, source="rxnorm", name=data['name'], tty=primary_tty)
            
            entity_id = generate_grc20_id()
            self.rxcui_to_entity[rxcui] = entity_id
            self.entity_index[entity_id] = len(self.entities)
            
            # Determine label based on tier
            if tier in ['Ingredient', 'PreciseIngredient', 'MultiIngredient']:
                label = 'Ingredient'
            elif tier == 'ClinicalDrug':
                label = 'ClinicalDrug'
            elif tier == 'BrandedDrug':
                label = 'BrandedDrug'
            elif tier == 'BrandName':
                label = 'BrandName'
            elif tier == 'DoseForm':
                label = 'DoseForm'
            else:
                label = 'RxNormConcept'
            
            triples = [
                create_triple(entity_id, "name", data['name']),
                create_triple(entity_id, "type", type_entities.get(label, type_entities['RxNormConcept'])),
                create_triple(entity_id, "rxcui", rxcui),
                create_triple(entity_id, "tty", primary_tty),
                create_triple(entity_id, "primary_tty", primary_tty),
                create_triple(entity_id, "tier", tier),
                create_triple(entity_id, "all_ttys", list(data['ttys'])),
                create_triple(entity_id, "provenance_rxnorm", prov_hash),
            ]
            
            if hierarchy_level:
                triples.append(create_triple(entity_id, "rxnorm_hierarchy_level", hierarchy_level))
            if hierarchy_desc:
                triples.append(create_triple(entity_id, "description", hierarchy_desc))
            
            self.entities.append({"space": "rxnorm", "entity": entity_id, "triples": triples})
            
            if (i + 1) % 50000 == 0:
                print(f"    {i + 1:,} entities...")
        
        print(f"  ✅ Created {len(self.entities):,} entities")
        
        # Create relationships
        print(f"  Creating {len(self.relationships):,} relationships...")
        
        rel_created = 0
        rel_attr_map = {
            'has_ingredient': 'has_ingredient',
            'has_dose_form': 'has_dose_form',
            'has_brand': 'has_brand',
            'SY': 'is_synonym',
            'SIMILAR_INGREDIENT': 'similar_ingredient',
        }
        
        for i, rel in enumerate(self.relationships):
            source_id = self.rxcui_to_entity.get(rel['source'])
            target_id = self.rxcui_to_entity.get(rel['target'])
            
            if not source_id or not target_id:
                continue
            
            rel_type = rel['relationship']
            attr_name = rel_attr_map.get(rel_type, f"rel_{rel_type.lower()}")
            
            rel_triple = create_relation(source_id, attr_name, target_id)
            
            idx = self.entity_index.get(source_id)
            if idx is not None:
                self.entities[idx]['triples'].append(rel_triple)
                rel_created += 1
            
            if (i + 1) % 100000 == 0:
                print(f"    {i + 1:,} relationships processed, {rel_created:,} created...")
        
        print(f"  ✅ Created {rel_created:,} relationship triples")
    
    def export(self, output_file: str) -> None:
        """Export GRC-20 data to JSON"""
        print(f"\n[4/5] Exporting to {output_file}...")
        
        output = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "source": "RxNorm (NLM)",
                "entity_types": {
                    "RxNormConcept": "Concept from RxNorm vocabulary",
                    "Ingredient": "Active ingredient (IN, PIN)",
                    "ClinicalDrug": "Semantic clinical drug (SCD)",
                    "BrandedDrug": "Semantic branded drug (SBD)",
                    "BrandName": "Brand name (BN)",
                    "DoseForm": "Dose form (DF)",
                },
                "stats": {
                    "total_entities": len(self.entities),
                    "total_concepts": len(self.concepts),
                    "total_relationships": len(self.relationships),
                    "tty_distribution": dict(self.tty_stats),
                    "rel_distribution": dict(self.rel_stats),
                }
            },
            "entities": self.entities
        }
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        size_mb = os.path.getsize(output_file) / 1024 / 1024
        print(f"  ✅ Exported {size_mb:.1f} MB")
    
    def run(self, zip_file: Optional[str] = None) -> str:
        """Run the full conversion pipeline"""
        print("=" * 80)
        print("RXNORM TO GRC-20 CONVERTER")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Find RxNorm files
        print("\n[1/5] Finding RxNorm files...")
        zip_files = self.find_rxnorm_files()
        
        if not zip_files:
            print("  ❌ No RxNorm zip files found")
            return ""
        
        if zip_file:
            self.selected_zip = zip_file
        else:
            self.selected_zip = zip_files[0]
        
        print(f"  ✅ Selected: {self.selected_zip}")
        
        # Extract
        print("\n[2/5] Extracting RxNorm files...")
        extract_dir = self.extract_rxnorm(self.selected_zip)
        print(f"  ✅ Extracted to: {extract_dir}")
        
        # Parse concepts
        print("\n[3/5] Parsing RxNorm data...")
        conso_file = self.find_rrf_file(extract_dir, "RXNCONSO.RRF")
        if conso_file:
            self.parse_concepts(conso_file)
        else:
            print("  ❌ RXNCONSO.RRF not found")
            return ""
        
        # Parse relationships
        rel_file = self.find_rrf_file(extract_dir, "RXNREL.RRF")
        if rel_file:
            self.parse_relationships(rel_file)
        
        # Enhance connectivity
        self.enhance_connectivity()
        
        # Convert to GRC-20
        self.convert_to_grc20()
        
        # Export
        output_file = os.path.join(OUTPUT_DIR, "grc20_rxnorm_data.json")
        self.export(output_file)
        
        # Summary
        print("\n" + "=" * 80)
        print("CONVERSION COMPLETE")
        print("=" * 80)
        stats = self.rel_stats
        print(f"Concepts: {len(self.concepts):,}")
        print(f"Entities: {len(self.entities):,}")
        print(f"Relationships: {len(self.relationships):,}")
        print("\nTop TTY types:")
        for tty, count in sorted(self.tty_stats.items(), key=lambda x: -x[1])[:10]:
            print(f"  • {TTY_DESCRIPTIONS.get(tty, tty)}: {count:,}")
        print("\nTop relationship types:")
        for rel, count in sorted(stats.items(), key=lambda x: -x[1])[:10]:
            print(f"  • {rel}: {count:,}")
        print("=" * 80)
        
        return output_file


if __name__ == "__main__":
    converter = RxNormGRC20Converter()
    output = converter.run()
