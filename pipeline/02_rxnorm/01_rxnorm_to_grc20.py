#!/usr/bin/env python3
"""
RxNorm to GRC-20 Converter v4.0
==============================

Converts RxNorm data (RXNCONSO.RRF, RXNREL.RRF) to GRC-20 format using
the new PharmaSchema v4 with proper UUID-based IDs.

Usage:
    python 01_rxnorm_to_grc20.py              # Interactive selection
    python 01_rxnorm_to_grc20.py --auto       # Use first available
    python 01_rxnorm_to_grc20.py --limit 1000 # Test mode
"""

import json
import os
import sys
import zipfile
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple
import argparse

# Add schema path
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '00_schema')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..')))
from pharma_schema import PharmaSchema, generate_uuid
from shared_state import save_source_selection

# =============================================================================
# FORCE SCHEMA REGENERATION
# =============================================================================
# Force schema regeneration by deleting the cache file if it exists
# This ensures the RxNorm converter uses the latest schema with correct IDs
CACHE_FILE_PATH = Path(__file__).parent.parent / "00_schema" / "schema_cache.json"
if CACHE_FILE_PATH.exists():
    try:
        CACHE_FILE_PATH.unlink()
        print(f"[INFO] Deleted existing schema cache: {CACHE_FILE_PATH}")
    except Exception as e:
        print(f"[WARNING] Could not delete schema cache: {e}")

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_DATA_DIR = f"{BASE_DIR}/data/raw_data"
EXTRACTED_DIR = f"{RAW_DATA_DIR}/extracted_rrf"
OUTPUT_DIR = f"{BASE_DIR}/data/grc20_v2"

# RxNorm TTY (Term Type) to Entity Type mapping - uses schema type names
TTY_TO_ENTITY_TYPE = {
    "IN": "Ingredient",
    "PIN": "PreciseIngredient",
    "MIN": "MultipleIngredient",
    "SCD": "ClinicalDrug",
    "SCDC": "ClinicalDrugComponent",
    "SCDF": "ClinicalDrugForm",
    "SCDG": "ClinicalDrugGroup",
    "SCDGP": "ClinicalDrugGroupPrecise",
    "SBD": "BrandedDrug",
    "SBDC": "BrandedDrugComponent",
    "SBDF": "BrandedDrugForm",
    "SBDG": "BrandedDrugGroup",
    "BN": "BrandName",
    "BNP": "BrandName",
    "DF": "DoseForm",
    "DFG": "DoseFormGroup",
    "GPCK": "GenericPack",
    "BPCK": "BrandPack",
    "PSN": "PrescribableName",
    "SY": "Synonym",
    "TMSY": "TallManSynonym",
    "SU": "SpecificSubstance",
}

# Primary TTYs for entity classification
PRIMARY_TTYS = set(TTY_TO_ENTITY_TYPE.keys())

# TTY priority for determining primary type
TTY_PRIORITY = [
    'SCD', 'SBD', 'MIN', 'IN', 'PIN', 'BN', 'SCDC', 'SBDC', 
    'DF', 'GPCK', 'BPCK', 'SU'
]

# TTY descriptions for reporting
TTY_DESCRIPTIONS = {
    'IN': 'Ingredient',
    'PIN': 'Precise Ingredient',
    'MIN': 'Multiple Ingredient',
    'SCDC': 'Semantic Clinical Drug Component',
    'SCDF': 'Semantic Clinical Drug Form',
    'SCDG': 'Semantic Clinical Drug Group',
    'SCD': 'Semantic Clinical Drug',
    'SBDC': 'Semantic Branded Drug Component',
    'SBDF': 'Semantic Branded Drug Form',
    'SBDG': 'Semantic Branded Drug Group',
    'SBD': 'Semantic Branded Drug',
    'BN': 'Brand Name',
    'DF': 'Dose Form',
    'DFG': 'Dose Form Group',
    'GPCK': 'Generic Pack',
    'BPCK': 'Brand Pack',
    'PSN': 'Prescribable Name',
    'SY': 'Synonym',
}

# RxNorm relationship to schema relation mapping
RXNREL_TO_SCHEMA_REL = {
    # Ingredient relationships
    "has_ingredient": "has_ingredient",
    "ingredient_of": "ingredient_of",
    "has_precise_ingredient": "has_precise_ingredient",
    "precise_ingredient_of": "precise_ingredient_of",
    "has_ingredients": "has_ingredients",
    "ingredients_of": "ingredients_of",
    
    # Dose form relationships  
    "has_dose_form": "has_dose_form",
    "dose_form_of": "dose_form_of",
    "has_doseformgroup": "has_doseformgroup",
    "doseformgroup_of": "doseformgroup_of",
    
    # Brand/tradename relationships
    "has_tradename": "has_tradename",
    "tradename_of": "tradename_of",
    "has_brand": "has_brand",
    
    # Hierarchy relationships
    "isa": "is_a",
    "inverse_isa": "inverse_isa",
    
    # Composition relationships
    "consists_of": "consists_of",
    "constitutes": "constitutes",
    "contains": "contains",
    "contained_in": "contained_in",
    
    # Part relationships
    "has_part": "has_part",
    "part_of": "part_of",
    "has_form": "has_form",
    "form_of": "form_of",
    
    # Reformulation relationships
    "reformulated_to": "reformulated_to",
    "reformulation_of": "reformulation_of",
    
    # Quantified form relationships
    "has_quantified_form": "has_quantified_form",
    "quantified_form_of": "quantified_form_of",
    
    # Boss (active moiety) relationships
    "has_boss": "has_boss",
    "boss_of": "boss_of",
    
    # Mapping relationships
    "mapped_to": "equivalent_to",
    "mapped_from": "equivalent_to",
}


# =============================================================================
# RXNORM GRC-20 CONVERTER
# =============================================================================

class RxNormGRC20Converter:
    """Convert RxNorm RRF files to GRC-20 format with schema v4 compliance."""
    
    def __init__(self, limit: Optional[int] = None):
        self.schema = PharmaSchema()
        self.limit = limit
        
        # Data storage
        self.concepts: Dict[str, dict] = {}
        self.raw_relationships: List[dict] = []
        self.entities: List[dict] = []
        self.relations: List[dict] = []
        
        # Indexes
        self.rxcui_to_entity: Dict[str, str] = {}
        
        # Provenance
        self.provenance_entity: Optional[dict] = None
        
        # Selected source
        self.selected_zip: Optional[str] = None
        self.selected_extract_dir: Optional[str] = None
        self.source_date: Optional[str] = None
        
        # Statistics
        self.stats = {
            "total_concepts": 0,
            "total_relationships": 0,
            "entities_by_type": defaultdict(int),
            "relationships_by_type": defaultdict(int),
        }
        self.tty_stats: Dict[str, int] = defaultdict(int)
        self.rel_stats: Dict[str, int] = defaultdict(int)
    
    def find_available_zips(self) -> List[str]:
        """Find available RxNorm zip files in raw_data directory."""
        zip_files = []
        if os.path.exists(RAW_DATA_DIR):
            for file in os.listdir(RAW_DATA_DIR):
                if file.startswith("RxNorm") and file.endswith(".zip"):
                    zip_files.append(file)
        return sorted(zip_files, reverse=True)
    
    def find_extracted_dirs(self) -> List[str]:
        """Find already extracted RxNorm directories."""
        extracted = []
        if os.path.exists(EXTRACTED_DIR):
            for subdir in os.listdir(EXTRACTED_DIR):
                full_path = os.path.join(EXTRACTED_DIR, subdir)
                if os.path.isdir(full_path) and "RxNorm" in subdir:
                    rrf_dir = os.path.join(full_path, "rrf")
                    if os.path.exists(rrf_dir):
                        extracted.append(subdir)
        return sorted(extracted, reverse=True)
    
    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """Extract date from RxNorm filename like RxNorm02022026.zip -> 2026-02-02."""
        match = re.search(r'RxNorm(\d{8})', filename)
        if match:
            date_str = match.group(1)
            return f"{date_str[4:8]}-{date_str[:2]}-{date_str[2:4]}"
        return None
    
    def select_source(self) -> Tuple[str, str]:
        """Let user select RxNorm source (zip or extracted)."""
        
        extracted = self.find_extracted_dirs()
        zips = self.find_available_zips()
        
        print("\n" + "=" * 70)
        print("RXNORM SOURCE SELECTION")
        print("=" * 70)
        
        options = []
        
        if extracted:
            print("\nExtracted RxNorm data (ready to use):")
            for i, dir_name in enumerate(extracted, 1):
                rrf_dir = os.path.join(EXTRACTED_DIR, dir_name, "rrf")
                conso_path = os.path.join(rrf_dir, "RXNCONSO.RRF")
                conso_size = os.path.getsize(conso_path) / 1024 / 1024 if os.path.exists(conso_path) else 0
                date_str = self.extract_date_from_filename(dir_name)
                date_info = f" (release: {date_str})" if date_str else ""
                print(f"  [{i}] {dir_name}{date_info} - {conso_size:.1f} MB")
                options.append(('extracted', dir_name))
        
        if zips:
            print("\nZip files (will need extraction):")
            for i, zip_name in enumerate(zips, len(options) + 1):
                zip_path = os.path.join(RAW_DATA_DIR, zip_name)
                zip_size = os.path.getsize(zip_path) / 1024 / 1024
                date_str = self.extract_date_from_filename(zip_name)
                date_info = f" (release: {date_str})" if date_str else ""
                print(f"  [{i}] {zip_name}{date_info} - {zip_size:.1f} MB")
                options.append(('zip', zip_name))
        
        if not options:
            raise FileNotFoundError("No RxNorm data found. Please download from NLM.")
        
        # Get user selection
        default = 1
        try:
            selection = input(f"\nSelect source [1-{len(options)}] (default: {default}): ").strip()
            if not selection:
                selection = default
            else:
                selection = int(selection)
            
            if selection < 1 or selection > len(options):
                print(f"Invalid selection, using default ({default})")
                selection = default
        except (ValueError, EOFError):
            print(f"Using default ({default})")
            selection = default
        
        # Process selection
        source_type, source_name = options[selection - 1]
        
        if source_type == 'extracted':
            self.selected_extract_dir = os.path.join(EXTRACTED_DIR, source_name)
            print(f"\nUsing extracted data: {source_name}")
            # Save selection for subsequent steps
            save_source_selection("RxNorm", self.selected_extract_dir, {
                "source_date": self.extract_date_from_filename(source_name)
            })
        else:
            print(f"\nExtracting {source_name}...")
            self.selected_extract_dir = self.extract_zip(source_name)
        
        # Extract date for provenance
        self.source_date = self.extract_date_from_filename(source_name)
        
        # Find RRF files
        rrf_dir = os.path.join(self.selected_extract_dir, "rrf")
        conso = os.path.join(rrf_dir, "RXNCONSO.RRF")
        rel = os.path.join(rrf_dir, "RXNREL.RRF")
        
        if not os.path.exists(conso) or not os.path.exists(rel):
            raise FileNotFoundError(f"RRF files not found in {rrf_dir}")
        
        return conso, rel
    
    def extract_zip(self, zip_name: str) -> str:
        """Extract RxNorm zip file."""
        extract_dir = os.path.join(EXTRACTED_DIR, zip_name.replace(".zip", "_extracted"))
        
        if os.path.exists(extract_dir):
            print(f"  Already extracted: {extract_dir}")
            return extract_dir
        
        os.makedirs(EXTRACTED_DIR, exist_ok=True)
        
        print(f"  Extracting to: {extract_dir}")
        zip_path = os.path.join(RAW_DATA_DIR, zip_name)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        
        print(f"  ✅ Extraction complete")
        return extract_dir
    
    def find_rrf_files_auto(self) -> Tuple[str, str]:
        """Find RRF files automatically (non-interactive)."""
        # Check extracted first
        extracted = self.find_extracted_dirs()
        if extracted:
            dir_name = extracted[0]  # Most recent
            self.selected_extract_dir = os.path.join(EXTRACTED_DIR, dir_name)
            self.source_date = self.extract_date_from_filename(dir_name)
            print(f"Using extracted data: {dir_name}")
        else:
            # Need to extract
            zips = self.find_available_zips()
            if not zips:
                raise FileNotFoundError("No RxNorm data found")
            zip_name = zips[0]
            print(f"Extracting {zip_name}...")
            self.selected_extract_dir = self.extract_zip(zip_name)
            self.source_date = self.extract_date_from_filename(zip_name)
        
        rrf_dir = os.path.join(self.selected_extract_dir, "rrf")
        conso = os.path.join(rrf_dir, "RXNCONSO.RRF")
        rel = os.path.join(rrf_dir, "RXNREL.RRF")
        
        if not os.path.exists(conso) or not os.path.exists(rel):
            raise FileNotFoundError(f"RRF files not found in {rrf_dir}")
        
        return conso, rel
    
    def create_provenance(self) -> None:
        """Create provenance entity for RxNorm import."""
        self.provenance_entity = self.schema.create_provenance_entity("RxNorm", self.source_date)
        self.entities.append(self.provenance_entity)
        print(f"  Created provenance: {self.provenance_entity['id']}")
        print(f"  Source: RxNorm")
        if self.source_date:
            print(f"  Source date: {self.source_date}")
    
    def parse_concepts(self, conso_file: str) -> None:
        """Parse RXNCONSO.RRF to extract concepts."""
        print(f"  Parsing concepts from {os.path.basename(conso_file)}...")
        
        with open(conso_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if self.limit and line_num > self.limit:
                    break
                if line_num % 100000 == 0:
                    print(f"    Line {line_num:,}...")
                
                fields = line.strip().split('|')
                if len(fields) < 15:
                    continue
                
                rxcui = fields[0]
                tty = fields[12]
                name = fields[14]
                
                if not rxcui or not name or not tty:
                    continue
                
                self.tty_stats[tty] += 1
                
                # Only process primary TTYs for entity creation
                if tty not in PRIMARY_TTYS:
                    continue
                
                if rxcui not in self.concepts:
                    self.concepts[rxcui] = {
                        'name': name,
                        'ttys': set(),
                        'tty_names': {},
                    }
                
                self.concepts[rxcui]['ttys'].add(tty)
                self.concepts[rxcui]['tty_names'][tty] = name
        
        print(f"  ✅ Parsed {len(self.concepts):,} unique RxCUIs")
    
    def parse_relationships(self, rel_file: str) -> None:
        """Parse RXNREL.RRF to extract relationships."""
        print(f"  Parsing relationships from {os.path.basename(rel_file)}...")
        
        with open(rel_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if self.limit and line_num > self.limit * 5:
                    break
                if line_num % 200000 == 0:
                    print(f"    Line {line_num:,}...")
                
                fields = line.strip().split('|')
                if len(fields) < 8:
                    continue
                
                source_rxcui = fields[0]
                target_rxcui = fields[4]
                relationship = fields[7]
                
                if not source_rxcui or not target_rxcui or not relationship:
                    continue
                
                # Only keep relationships between concepts we have
                if source_rxcui not in self.concepts or target_rxcui not in self.concepts:
                    continue
                
                # Only keep mapped relationships
                if relationship not in RXNREL_TO_SCHEMA_REL:
                    continue
                
                # Get source/target TTYs for relationship metadata
                source_tty = next(iter(self.concepts[source_rxcui]['ttys']), None)
                target_tty = next(iter(self.concepts[target_rxcui]['ttys']), None)
                
                self.raw_relationships.append({
                    'source': source_rxcui,
                    'target': target_rxcui,
                    'relationship': relationship,
                    'source_tty': source_tty,
                    'target_tty': target_tty,
                })
                self.rel_stats[relationship] += 1
        
        print(f"  ✅ Parsed {len(self.raw_relationships):,} relationships")
    
    def determine_primary_tty(self, ttys: Set[str]) -> Optional[str]:
        """Determine primary TTY from set of TTYs."""
        primary_ttys = [t for t in ttys if t in PRIMARY_TTYS]
        if not primary_ttys:
            return None
        for tty in TTY_PRIORITY:
            if tty in primary_ttys:
                return tty
        return primary_ttys[0]
    
    def create_entities(self) -> None:
        """Create GRC-20 entities from parsed concepts."""
        print("\n[4/6] Creating GRC-20 entities...")
        
        for rxcui, data in self.concepts.items():
            primary_tty = self.determine_primary_tty(data['ttys'])
            if not primary_tty:
                continue
            
            entity_type = TTY_TO_ENTITY_TYPE.get(primary_tty, "DrugProduct")
            name = data['tty_names'].get(primary_tty, data['name'])
            
            # Create deterministic entity ID from RxCUI
            entity_id = generate_uuid(seed=f"rxnorm_rxcui_{rxcui}")
            
            # Create entity using new schema API
            entity = self.schema.create_entity(
                entity_type=entity_type,
                name=name,
                entity_id=entity_id,
                rxcui=rxcui,
                tty=primary_tty,
            )
            
            # Add all TTYs as additional property
            all_ttys = sorted(data['ttys'])
            if len(all_ttys) > 1:
                # Store as comma-separated string for now
                # Could also create separate entities for each TTY variant
                pass
            
            # Add provenance relation
            prov_relation = self.schema.add_provenance_relation(entity_id, "RxNorm")
            self.relations.append(prov_relation)
            
            # Index and store
            self.rxcui_to_entity[rxcui] = entity_id
            self.entities.append(entity)
            self.stats["entities_by_type"][entity_type] += 1
        
        self.stats["total_concepts"] = len(self.entities) - 1  # Exclude provenance entity
        print(f"  ✅ Created {self.stats['total_concepts']:,} entities")
        for entity_type, count in sorted(self.stats["entities_by_type"].items()):
            print(f"     {entity_type}: {count:,}")
    
    def create_relations(self) -> None:
        """Create GRC-20 relations from parsed relationships."""
        print("\n[5/6] Creating GRC-20 relations...")
        
        created = 0
        seen = set()
        
        for rel in self.raw_relationships:
            source_id = self.rxcui_to_entity.get(rel['source'])
            target_id = self.rxcui_to_entity.get(rel['target'])
            
            if not source_id or not target_id:
                continue
            
            rel_type = RXNREL_TO_SCHEMA_REL.get(rel['relationship'])
            if not rel_type:
                continue
            
            # Deduplicate
            key = (source_id, rel_type, target_id)
            if key in seen:
                continue
            seen.add(key)
            
            # Create deterministic relation ID
            relation_id = generate_uuid(
                seed=f"rxnorm_rel_{rel['source']}_{rel['relationship']}_{rel['target']}"
            )
            
            # Create relation using new schema API
            relation = self.schema.create_relation(
                from_entity_id=source_id,
                relation_type=rel_type,
                to_entity_id=target_id,
                relation_id=relation_id,
                rela_code=rel['relationship'],
                source_tty=rel.get('source_tty'),
                target_tty=rel.get('target_tty'),
            )
            
            self.relations.append(relation)
            self.stats["relationships_by_type"][rel_type] += 1
            created += 1
        
        self.stats["total_relationships"] = created
        print(f"  ✅ Created {created:,} relations")
        for rel_type, count in sorted(self.stats["relationships_by_type"].items()):
            print(f"     {rel_type}: {count:,}")
    
    def export(self, output_dir: str) -> None:
        """Export GRC-20 data to JSONL files for Geo SDK import."""
        print(f"\n[6/6] Exporting to {output_dir}...")
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Export entities
        entities_file = os.path.join(output_dir, "rxnorm_entities.jsonl")
        with open(entities_file, 'w', encoding='utf-8') as f:
            for entity in self.entities:
                f.write(json.dumps(entity) + '\n')
        
        # Export relations
        relations_file = os.path.join(output_dir, "rxnorm_relations.jsonl")
        with open(relations_file, 'w', encoding='utf-8') as f:
            for relation in self.relations:
                f.write(json.dumps(relation) + '\n')
        
        # Export summary
        summary = {
            "exported_at": datetime.now().isoformat(),
            "schema_version": self.schema.metadata.get("version", "4.0.0"),
            "source": "RxNorm",
            "source_file": os.path.basename(self.selected_extract_dir) if self.selected_extract_dir else None,
            "source_date": self.source_date,
            "stats": {
                "total_entities": len(self.entities),
                "total_relations": len(self.relations),
                "provenance_entities": 1,
                "data_entities": self.stats["total_concepts"],
                "entities_by_type": dict(self.stats["entities_by_type"]),
                "relationships_by_type": dict(self.stats["relationships_by_type"]),
                "tty_distribution": dict(self.tty_stats),
            }
        }
        
        summary_file = os.path.join(output_dir, "rxnorm_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        # Calculate sizes
        entities_size = os.path.getsize(entities_file) / 1024 / 1024
        relations_size = os.path.getsize(relations_file) / 1024 / 1024
        
        print(f"  ✅ Exported:")
        print(f"     entities.jsonl: {entities_size:.1f} MB ({len(self.entities):,} entities)")
        print(f"     relations.jsonl: {relations_size:.1f} MB ({len(self.relations):,} relations)")
        print(f"     summary.json: {summary_file}")
    
    def run(self, auto: bool = False) -> str:
        """Run the full conversion pipeline."""
        print("=" * 70)
        print("RXNORM TO GRC-20 CONVERTER v4.0")
        print("=" * 70)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Find/select files
        print("\n[1/6] Finding RxNorm source...")
        if auto:
            conso_file, rel_file = self.find_rrf_files_auto()
        else:
            conso_file, rel_file = self.select_source()
        
        # Create provenance
        print("\n[2/6] Creating provenance...")
        self.create_provenance()
        
        # Parse
        print("\n[3/6] Parsing RxNorm files...")
        self.parse_concepts(conso_file)
        self.parse_relationships(rel_file)
        
        # Convert
        self.create_entities()
        self.create_relations()
        
        # Export
        self.export(OUTPUT_DIR)
        
        # Summary
        print("\n" + "=" * 70)
        print("CONVERSION COMPLETE")
        print("=" * 70)
        print(f"Entities: {len(self.entities):,}")
        print(f"Relations: {len(self.relations):,}")
        print("\nTop TTY types:")
        for tty, count in sorted(self.tty_stats.items(), key=lambda x: -x[1])[:10]:
            desc = TTY_DESCRIPTIONS.get(tty, tty)
            print(f"  • {desc}: {count:,}")
        print("\nTop relationship types:")
        for rel, count in sorted(self.rel_stats.items(), key=lambda x: -x[1])[:10]:
            print(f"  • {rel}: {count:,}")
        print("=" * 70)
        
        return OUTPUT_DIR


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert RxNorm to GRC-20 format v4.0")
    parser.add_argument("--auto", action="store_true", help="Auto-select first available source (no prompts)")
    parser.add_argument("--limit", type=int, help="Limit number of concepts (for testing)")
    args = parser.parse_args()
    
    converter = RxNormGRC20Converter(limit=args.limit)
    output = converter.run(auto=args.auto)
