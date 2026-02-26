#!/usr/bin/env python3
"""
GRC-20 Merger & Enricher
========================

Merges GRC-20 triple files and enriches with additional properties.

GRC-20 Spec Compliance:
- Relations are first-class entities with from_entity, to_entity, and type
- This file maintains that structure for spec compliance
- Also extracts relationships array for Neo4j convenience

Input:
- rxnorm_entities.json (GRC-20) - RxNorm ingredients + relations
- ndc_bridge_entities.json (GRC-20) - NDC entities + relations  
- pubchem_properties.json (staging) - PubChem properties to enrich

Output:
- grc20_merged.json - Combined GRC-20 entities with:
  - entities: all entities including relations (GRC-20 compliant)
  - nodes: entity IDs that are NOT relations (nouns)
  - relations: entity IDs that ARE relations (verbs/edges)
  - relationships: extracted edges for Neo4j loading

Usage:
    python 01_merge_enrich.py [--output FILE]
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR = BASE_DIR / "data" / "grc20_v2"
DEFAULT_OUTPUT = DATA_DIR / "grc20_merged.json"

# GRC-20 Spec IDs for relation attributes
GRC20_FROM_ENTITY = "RERshk4JoYoMC17r1qAo9J"
GRC20_TO_ENTITY = "Qx8dASiTNsxxP3rJbd4Lzd"
GRC20_TYPE = "Jfmby78N4BCseZinBmdVov"  # Types attribute

# GRC-20 System Types (to filter out when finding relation types)
GRC20_SYSTEM_TYPES = {
    "Type": "Jfmby78N4BCseZinBmdVov",
    "Attribute": "GscJ2GELQjmLoaVrYyR3xm",
    "Relation": "QtC4Ay8HNLwSd1kSARgcDE",
    "RelationType": "3WxYoAVreE4qFhkDUs5J3q",
}
GRC20_SYSTEM_TYPE_IDS = set(GRC20_SYSTEM_TYPES.values())

# Add schema path
sys.path.insert(0, str(Path(__file__).parent.parent / "00_schema"))
from pharma_schema import PharmaSchema


class GRC20Merger:
    """Merges GRC-20 files and enriches with properties."""
    
    def __init__(self):
        self.schema = PharmaSchema()
        self.entities = {}  # entity_id -> entity dict
        self.stats = {
            "rxnorm_entities": 0,
            "ndc_entities": 0,
            "enriched": 0,
            "properties_added": 0,
            "properties_skipped": 0,
            "total_entities": 0,
            "nodes": 0,
            "relations": 0,
        }
        self.skipped_attributes = defaultdict(int)
        
        # Build reverse lookup for relation types
        self.rel_id_to_name = {id_: name for name, id_ in self.schema.relations.items()}
        
    def merge_all(self):
        """Run full merge pipeline."""
        print("=" * 70)
        print("GRC-20 MERGER & ENRICHER")
        print("=" * 70)
        
        # Step 1: Load RxNorm entities (includes relations as entities)
        self.load_grc20_file(DATA_DIR / "rxnorm_entities.json", "RxNorm")
        
        # Step 2: Load NDC bridge (includes relations as entities)
        self.load_grc20_file(DATA_DIR / "ndc_bridge_entities.json", "NDC Bridge")
        
        # Step 3: Enrich with PubChem
        self.enrich_pubchem()
        
        # Step 4: Classify entities (nodes vs relations)
        self.classify_entities()
        
    def load_grc20_file(self, filepath: Path, source_name: str):
        """Load and merge a GRC-20 JSON file."""
        print(f"\n[{source_name}] Loading {filepath.name}...")
        
        if not filepath.exists():
            print(f"  ⚠️ File not found: {filepath}")
            return
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        entities = data.get("entities", [])
        file_stats = data.get("stats", {})
        
        print(f"  Found {len(entities):,} entities")
        if file_stats.get("relationships_by_type"):
            print(f"  Relations in file: {file_stats.get('relations', 0):,}")
            for rel_type, count in file_stats["relationships_by_type"].items():
                print(f"    - {rel_type}: {count:,}")
        
        new_entities = 0
        merged_triples = 0
        
        for entity in entities:
            entity_id = entity.get("entity")
            if not entity_id:
                continue
            
            if entity_id in self.entities:
                # Merge triples into existing entity
                existing_triples = {self._triple_key(t): t for t in self.entities[entity_id].get("triples", [])}
                for new_triple in entity.get("triples", []):
                    key = self._triple_key(new_triple)
                    if key not in existing_triples:
                        self.entities[entity_id]["triples"].append(new_triple)
                        merged_triples += 1
            else:
                # New entity
                self.entities[entity_id] = entity
                new_entities += 1
        
        if source_name == "RxNorm":
            self.stats["rxnorm_entities"] = new_entities
        elif source_name == "NDC Bridge":
            self.stats["ndc_entities"] = new_entities
        
        print(f"  ✅ Added {new_entities:,} new entities, merged {merged_triples:,} triples")
        
    def _triple_key(self, triple: dict) -> str:
        """Create a unique key for a triple (for deduplication)."""
        attr = triple.get("attribute", "")
        val = triple.get("value", {})
        return f"{attr}|{val.get('type', '')}|{val.get('value', '')}"
    
    def enrich_pubchem(self):
        """Enrich entities with PubChem properties."""
        print("\n[PubChem] Enriching with properties...")
        
        pubchem_file = DATA_DIR / "pubchem_properties.json"
        if not pubchem_file.exists():
            print(f"  ⚠️ File not found: {pubchem_file}")
            return
        
        with open(pubchem_file, 'r') as f:
            data = json.load(f)
        
        enriched_cids = data.get("enriched_cids", {})
        print(f"  Found {len(enriched_cids):,} enrichment records")
        
        # Build RxCUI -> entity_id lookup from current entities
        rxcui_to_entity = {}
        for entity_id, entity in self.entities.items():
            for t in entity.get("triples", []):
                if t.get("attribute") == "rxcui":  # Will need to use attr ID
                    rxcui = t.get("value", {}).get("value")
                    if rxcui:
                        rxcui_to_entity[rxcui] = entity_id
        
        print(f"  Built RxCUI lookup with {len(rxcui_to_entity):,} mappings")
        
        for rxcui, cid_data in enriched_cids.items():
            # Try to find entity by RxCUI first
            entity_id = rxcui_to_entity.get(rxcui) or cid_data.get("entity_id")
            if not entity_id or entity_id not in self.entities:
                continue
            
            entity = self.entities[entity_id]
            properties = cid_data.get("properties", {})
            
            # Build lookup of existing triples to avoid duplicates
            existing = {self._triple_key(t): t for t in entity.get("triples", [])}
            
            # Add property triples (only schema-supported attributes)
            supported_attrs = {"smiles", "inchikey", "iupac_name", "pubchem_cid"}
            
            for prop_key, value in properties.items():
                if not value:
                    continue
                
                if prop_key not in supported_attrs:
                    self.skipped_attributes[prop_key] += 1
                    self.stats["properties_skipped"] += 1
                    continue
                
                # Create triple with attribute name (will be converted to ID by loader)
                triple = {
                    "entity": entity_id,
                    "attribute": prop_key,
                    "value": {"type": 1, "value": str(value)},
                }
                
                key = self._triple_key(triple)
                if key not in existing:
                    entity["triples"].append(triple)
                    existing[key] = triple
                    self.stats["properties_added"] += 1
            
            # Add CID
            cid = cid_data.get("cid")
            if cid:
                triple = {
                    "entity": entity_id,
                    "attribute": "pubchem_cid",
                    "value": {"type": 2, "value": int(cid)},  # Type 2 = NUMBER
                }
                key = self._triple_key(triple)
                if key not in existing:
                    entity["triples"].append(triple)
                    self.stats["properties_added"] += 1
            
            self.stats["enriched"] += 1
        
        print(f"  ✅ Enriched {self.stats['enriched']:,} entities")
        print(f"  ✅ Added {self.stats['properties_added']:,} property triples")
    
    def classify_entities(self):
        """
        Classify entities as nodes (nouns) or relations (verbs/edges).
        
        Per GRC-20 spec:
        - Relations are entities with from_entity and to_entity attributes
        - Nodes are all other entities
        """
        print("\n[Classifying] Distinguishing nodes from relations...")
        
        self.node_ids = set()
        self.relation_ids = set()
        self.relationships = []  # For Neo4j: {from, to, type, type_name, entity_id}
        
        for entity_id, entity in self.entities.items():
            triples = entity.get("triples", [])
            
            # Check if this is a relation entity (has from_entity and to_entity)
            from_entity = None
            to_entity = None
            all_types = []  # Collect all type values
            
            for t in triples:
                attr = t.get("attribute", "")
                val = t.get("value", {}).get("value", "")
                
                if attr == GRC20_FROM_ENTITY:
                    from_entity = val
                elif attr == GRC20_TO_ENTITY:
                    to_entity = val
                elif attr == GRC20_TYPE:
                    all_types.append(val)
            
            if from_entity and to_entity:
                # This is a relation entity (edge/verb)
                self.relation_ids.add(entity_id)
                
                # Find the actual relation type by filtering out system types
                relation_type_id = None
                for type_val in all_types:
                    if type_val not in GRC20_SYSTEM_TYPE_IDS:
                        relation_type_id = type_val
                        break
                
                # Get human-readable type name
                type_name = self.rel_id_to_name.get(relation_type_id, "unknown")
                
                self.relationships.append({
                    "entity_id": entity_id,  # Reference to full relation entity
                    "from": from_entity,
                    "to": to_entity,
                    "type": relation_type_id,  # GRC-20 type ID
                    "type_name": type_name,  # Human-readable name for Neo4j
                })
            else:
                # This is a node entity (noun)
                self.node_ids.add(entity_id)
        
        self.stats["nodes"] = len(self.node_ids)
        self.stats["relations"] = len(self.relation_ids)
        
        print(f"  ✅ Nodes (nouns): {self.stats['nodes']:,}")
        print(f"  ✅ Relations (verbs): {self.stats['relations']:,}")
        
    def export(self, filepath: Path):
        """Export merged entities to GRC-20 JSON."""
        print("\n" + "=" * 70)
        print("EXPORTING")
        print("=" * 70)
        
        # Count relationship types
        rel_type_counts = defaultdict(int)
        for rel in self.relationships:
            rel_type_counts[rel["type_name"]] += 1
        
        output = {
            "space": "pharma",
            "version": "2.0.0",
            "exported_at": datetime.now().isoformat(),
            "schema_version": "1.1.0",
            "source": "rxnorm_entities.json + ndc_bridge_entities.json + pubchem_properties.json",
            "stats": {
                "total_entities": len(self.entities),
                "nodes": self.stats["nodes"],
                "relations": self.stats["relations"],
                "rxnorm_entities": self.stats["rxnorm_entities"],
                "ndc_entities": self.stats["ndc_entities"],
                "enriched": self.stats["enriched"],
                "properties_added": self.stats["properties_added"],
                "relationship_types": dict(sorted(rel_type_counts.items(), key=lambda x: -x[1])),
            },
            # GRC-20 compliant: all entities in one array
            "entities": list(self.entities.values()),
            # Convenience for Neo4j and queries
            "node_ids": list(self.node_ids),
            "relation_ids": list(self.relation_ids),
            "relationships": self.relationships,
        }
        
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)
        
        size_mb = filepath.stat().st_size / 1024 / 1024
        
        print(f"  ✅ Exported to: {filepath}")
        print(f"  File size: {size_mb:.1f} MB")
        print(f"  Total entities: {len(self.entities):,}")
        print(f"    - Nodes (nouns): {self.stats['nodes']:,}")
        print(f"    - Relations (verbs): {self.stats['relations']:,}")
        print(f"  Relationships array: {len(self.relationships):,} edges for Neo4j")
        
        if self.skipped_attributes:
            print("\n  ⚠️  SKIPPED ATTRIBUTES (not in schema):")
            for attr, count in sorted(self.skipped_attributes.items(), key=lambda x: -x[1]):
                print(f"     - {attr}: {count:,} values")
        
        print("\n  Top relationship types:")
        for type_name, count in sorted(rel_type_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    - {type_name}: {count:,}")


def main():
    parser = argparse.ArgumentParser(description="Merge GRC-20 files and enrich")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Output file path")
    args = parser.parse_args()
    
    merger = GRC20Merger()
    merger.merge_all()
    merger.export(args.output)


if __name__ == "__main__":
    main()
