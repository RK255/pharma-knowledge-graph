#!/usr/bin/env python3
"""
GRC-20 Merger & Enricher
========================
Merges GRC-20 JSONL entity and relation files, enriches with PubChem properties.
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import uuid

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
DEFAULT_OUTPUT = DATA_DIR / "grc20_merged"

# Add schema path
sys.path.insert(0, str(Path(__file__).parent.parent / "00_schema"))
from pharma_schema import PharmaSchema

class GRC20Merger:
    """Merges GRC-20 JSONL files and enriches with properties."""
    
    def __init__(self):
        self.schema = PharmaSchema()
        self.entities = {}  # id -> entity dict
        self.relations = {}  # id -> relation dict
        self.stats = {
            "rxnorm_entities": 0,
            "rxnorm_relations": 0,
            "ndc_entities": 0,
            "ndc_relations": 0,
            "dailymed_entities": 0,
            "pubchem_entities": 0,
            "pubchem_relations": 0,
            "enriched": 0,
            "properties_added": 0,
            "total_entities": 0,
            "total_relations": 0,
        }
        self.rel_id_to_name = {id_: name for name, id_ in self.schema.relations.items()}
        
    def merge_all(self):
        print("=" * 70)
        print("GRC-20 MERGER & ENRICHER")
        print("=" * 70)
        
        # Load RxNorm
        self.load_entities_jsonl(DATA_DIR / "rxnorm_entities.jsonl", "RxNorm")
        self.load_relations_jsonl(DATA_DIR / "rxnorm_relations.jsonl", "RxNorm")
        
        # Load DailyMed
        self.load_entities_jsonl(DATA_DIR / "dailymed_entities.jsonl", "DailyMed")
        self.load_relations_jsonl(DATA_DIR / "dailymed_relations.jsonl", "DailyMed")
        
        # Load NDC Bridge
        self.load_entities_jsonl(DATA_DIR / "ndc_bridge_entities.jsonl", "NDC Bridge")
        self.load_relations_jsonl(DATA_DIR / "ndc_bridge_relations.jsonl", "NDC Bridge")
        
        # Load PubChem
        self.load_entities_jsonl(DATA_DIR / "pubchem_entities.jsonl", "PubChem")
        self.load_relations_jsonl(DATA_DIR / "pubchem_relations.jsonl", "PubChem")
        self.load_entities_jsonl(DATA_DIR / "pubchem_properties_entities.jsonl", "PubChem Properties")
        self.load_relations_jsonl(DATA_DIR / "pubchem_properties_relations.jsonl", "PubChem Properties")
        
        # Enrich with PubChem data
        self.enrich_pubchem()
        
        # Export
        self.export_jsonl(DEFAULT_OUTPUT)
        
    def load_entities_jsonl(self, filepath: Path, source_name: str):
        """Load entities from JSONL file."""
        if not filepath.exists():
            print(f"\n[{source_name}] ⚠️ Entities file not found: {filepath.name}")
            return
        
        print(f"\n[{source_name}] Loading entities: {filepath.name}...")
        count = 0
        new_count = 0
        
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entity = json.loads(line)
                entity_id = entity.get("id")
                if entity_id and entity_id not in self.entities:
                    self.entities[entity_id] = entity
                    new_count += 1
                count += 1
        
        self.stats[f"{source_name.lower().replace(' ', '_')}_entities"] = new_count
        print(f"  ✅ Loaded {count:,} entities ({new_count:,} new)")
        
    def load_relations_jsonl(self, filepath: Path, source_name: str):
        """Load relations from JSONL file."""
        if not filepath.exists():
            print(f"\n[{source_name}] ⚠️ Relations file not found: {filepath.name}")
            return
        
        print(f"[{source_name}] Loading relations: {filepath.name}...")
        count = 0
        new_count = 0
        
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                relation = json.loads(line)
                relation_id = relation.get("id")
                if relation_id and relation_id not in self.relations:
                    self.relations[relation_id] = relation
                    new_count += 1
                count += 1
        
        self.stats[f"{source_name.lower().replace(' ', '_')}_relations"] = new_count
        print(f"  ✅ Loaded {count:,} relations ({new_count:,} new)")
        
    def enrich_pubchem(self):
        """Enrich entities with PubChem properties from pubchem_properties.json."""
        print("\n[PubChem] Enriching with properties...")
        pubchem_file = DATA_DIR / "pubchem_properties.json"
        if not pubchem_file.exists():
            print(f"  ⚠️ File not found: {pubchem_file}")
            return
        
        with open(pubchem_file, 'r') as f:
            data = json.load(f)
        
        enriched_cids = data.get("enriched_cids", {})
        print(f"  Found {len(enriched_cids):,} enrichment records")
        
        # Build RxCUI to entity lookup
        rxcui_prop_id = self.schema.prop("rxcui")
        rxcui_to_entity = {}
        
        for entity_id, entity in self.entities.items():
            for v in entity.get("values", []):
                if v.get("property") == rxcui_prop_id:
                    rxcui = str(v.get("value", ""))
                    if rxcui:
                        rxcui_to_entity[rxcui] = entity_id
        
        print(f"  Built RxCUI lookup with {len(rxcui_to_entity):,} mappings")
        
        # Supported properties (PubChem enrichment)
        supported_props = {
            "mesh_classes": self.schema.prop("mesh_classes"),
            "smiles": self.schema.prop("smiles"),
            "inchikey": self.schema.prop("inchikey"),
            "iupac_name": self.schema.prop("iupac_name"),
            "pubchem_cid": self.schema.prop("pubchem_cid"),
            "molecular_formula": self.schema.prop("molecular_formula"),
            "molecular_weight": self.schema.prop("molecular_weight"),
            "pubchem_date": self.schema.prop("pubchem_date"),
            "pmid": self.schema.prop("pmid"),
            "sid": self.schema.prop("sid"),
        }
        
        for rxcui, cid_data in enriched_cids.items():
            entity_id = rxcui_to_entity.get(rxcui) or cid_data.get("entity_id")
            if not entity_id or entity_id not in self.entities:
                continue
            
            entity = self.entities[entity_id]
            properties = cid_data.get("properties", {})
            existing_props = {v.get("property") for v in entity.get("values", [])}
            
            for prop_key, value in properties.items():
                if not value:
                    continue
                prop_id = supported_props.get(prop_key)
                if not prop_id:
                    continue
                if prop_id in existing_props:
                    continue
                
                entity.setdefault("values", []).append({
                    "property": prop_id,
                    "value": str(value)
                })
                self.stats["properties_added"] += 1
            
            self.stats["enriched"] += 1
        
        print(f"  ✅ Enriched {self.stats['enriched']:,} entities")
        print(f"  ✅ Added {self.stats['properties_added']:,} properties")
        
    def export_jsonl(self, output_path: Path):
        """Export merged data as JSONL files."""
        print("\n" + "=" * 70)
        print("EXPORTING")
        print("=" * 70)
        
        # Export entities
        entities_file = f"{output_path}_entities.jsonl"
        with open(entities_file, 'w') as f:
            for entity in self.entities.values():
                f.write(json.dumps(entity) + "\n")
        
        size_mb = Path(entities_file).stat().st_size / 1024 / 1024
        print(f"  ✅ Entities: {entities_file} ({size_mb:.1f} MB)")
        
        # Export relations
        relations_file = f"{output_path}_relations.jsonl"
        with open(relations_file, 'w') as f:
            for relation in self.relations.values():
                f.write(json.dumps(relation) + "\n")
        
        size_mb = Path(relations_file).stat().st_size / 1024 / 1024
        print(f"  ✅ Relations: {relations_file} ({size_mb:.1f} MB)")
        
        # Count relation types
        rel_type_counts = defaultdict(int)
        for rel in self.relations.values():
            type_id = rel.get("type", "unknown")
            type_name = self.rel_id_to_name.get(type_id, type_id[:8])
            rel_type_counts[type_name] += 1
        
        print(f"\n  Relation types:")
        for name, count in sorted(rel_type_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {name}: {count:,}")
        
        print(f"\n  Stats:")
        print(f"    Total entities: {len(self.entities):,}")
        print(f"    Total relations: {len(self.relations):,}")
        print(f"    Enriched: {self.stats['enriched']:,}")
        print(f"    Properties added: {self.stats['properties_added']:,}")


def main():
    parser = argparse.ArgumentParser(description="Merge GRC-20 files")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path prefix")
    args = parser.parse_args()
    
    merger = GRC20Merger()
    merger.merge_all()


if __name__ == "__main__":
    main()
