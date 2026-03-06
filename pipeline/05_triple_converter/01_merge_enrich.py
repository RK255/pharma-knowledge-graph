#!/usr/bin/env python3
"""
GRC-20 Merger & Enricher
========================
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
DEFAULT_OUTPUT = DATA_DIR / "grc20_merged.json"

# GRC-20 Spec IDs for relation attributes
GRC20_FROM_ENTITY = "RERshk4JoYoMC17r1qAo9J"
GRC20_TO_ENTITY = "Qx8dASiTNsxxP3rJbd4Lzd"
GRC20_TYPE = "Jfmby78N4BCseZinBmdVov"

# Add schema path
sys.path.insert(0, str(Path(__file__).parent.parent / "00_schema"))
from pharma_schema import PharmaSchema

class GRC20Merger:
    """Merges GRC-20 files and enriches with properties."""
    
    def __init__(self):
        self.schema = PharmaSchema()
        self.entities = {}
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
        self.rel_id_to_name = {id_: name for name, id_ in self.schema.relations.items()}
        
    def merge_all(self):
        print("=" * 70)
        print("GRC-20 MERGER & ENRICHER")
        print("=" * 70)
        self.load_grc20_file(DATA_DIR / "rxnorm_entities.json", "RxNorm")
        self.load_grc20_file(DATA_DIR / "ndc_bridge_entities.json", "NDC Bridge")
        self.load_grc20_file(DATA_DIR / "dailymed_entities.json", "DailyMed")
        self.enrich_pubchem()
        self.classify_entities()
        
    def load_grc20_file(self, filepath: Path, source_name: str):
        print(f"\n[{source_name}] Loading {filepath.name}...")
        if not filepath.exists():
            print(f"  ⚠️ File not found: {filepath}")
            return
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        entities = data.get("entities", [])
        print(f"  Found {len(entities):,} entities")
        
        new_entities = 0
        merged_triples = 0
        
        for entity in entities:
            entity_id = entity.get("entity")
            if not entity_id:
                continue
            
            if entity_id in self.entities:
                existing_triples = {self._triple_key(t): t for t in self.entities[entity_id].get("triples", [])}
                for new_triple in entity.get("triples", []):
                    key = self._triple_key(new_triple)
                    if key not in existing_triples:
                        self.entities[entity_id]["triples"].append(new_triple)
                        merged_triples += 1
            else:
                self.entities[entity_id] = entity
                new_entities += 1
        
        print(f"  ✅ Added {new_entities:,} new entities, merged {merged_triples:,} triples")

    def _triple_key(self, triple: dict) -> str:
        val = triple.get("value", {})
        return f"{triple.get('attribute', '')}|{val.get('type', '')}|{val.get('value', '')}"
    
    def enrich_pubchem(self):
        print("\n[PubChem] Enriching with properties...")
        pubchem_file = DATA_DIR / "pubchem_properties.json"
        if not pubchem_file.exists():
            print(f"  ⚠️ File not found: {pubchem_file}")
            return
        
        with open(pubchem_file, 'r') as f:
            data = json.load(f)
        
        enriched_cids = data.get("enriched_cids", {})
        print(f"  Found {len(enriched_cids):,} enrichment records")
        
        rxcui_to_entity = {}
        rxcui_attr_id = self.schema.attr("rxcui")
        
        for entity_id, entity in self.entities.items():
            for t in entity.get("triples", []):
                if t.get("attribute") == rxcui_attr_id:
                    rxcui = t.get("value", {}).get("value")
                    if rxcui:
                        rxcui_to_entity[str(rxcui)] = entity_id
        
        print(f"  Built RxCUI lookup with {len(rxcui_to_entity):,} mappings")
        
        for rxcui, cid_data in enriched_cids.items():
            entity_id = rxcui_to_entity.get(rxcui) or cid_data.get("entity_id")
            if not entity_id or entity_id not in self.entities:
                continue
            
            entity = self.entities[entity_id]
            properties = cid_data.get("properties", {})
            existing = {self._triple_key(t): t for t in entity.get("triples", [])}
            
            supported_attrs = {"smiles", "inchikey", "iupac_name", "pubchem_cid", "mesh_classes"}
            
            for prop_key, value in properties.items():
                if not value: continue
                if prop_key not in supported_attrs:
                    self.skipped_attributes[prop_key] += 1
                    continue
                
                triple = {
                    "entity": entity_id,
                    "attribute": self.schema.attr(prop_key),
                    "value": {"type": 1, "value": str(value)},
                }
                key = self._triple_key(triple)
                if key not in existing:
                    entity["triples"].append(triple)
                    self.stats["properties_added"] += 1
            
            cid = cid_data.get("cid")
            if cid:
                triple = {
                    "entity": entity_id,
                    "attribute": self.schema.attr("pubchem_cid"),
                    "value": {"type": 2, "value": int(cid)},
                }
                key = self._triple_key(triple)
                if key not in existing:
                    entity["triples"].append(triple)
                    self.stats["properties_added"] += 1
            
            prov_id = data.get("provenance_entity")
            if prov_id:
                prov_triple = {
                    "entity": entity_id,
                    "attribute": self.schema.attr("provenance"),
                    "value": {"type": 1, "value": prov_id},
                }
                if self._triple_key(prov_triple) not in existing:
                    entity["triples"].append(prov_triple)
            
            self.stats["enriched"] += 1
        
        print(f"  ✅ Enriched {self.stats['enriched']:,} entities")
    
    def classify_entities(self):
        print("\n[Classifying] Distinguishing nodes from relations...")
        self.node_ids = set()
        self.relation_ids = set()
        self.relationships = []
        
        for entity_id, entity in self.entities.items():
            triples = entity.get("triples", [])
            from_entity = None
            to_entity = None
            all_types = []
            
            for t in triples:
                attr = t.get("attribute", "")
                val = t.get("value", {}).get("value", "")
                if attr == GRC20_FROM_ENTITY: from_entity = val
                elif attr == GRC20_TO_ENTITY: to_entity = val
                elif attr == GRC20_TYPE: all_types.append(val)
            
            if from_entity and to_entity:
                self.relation_ids.add(entity_id)
                relation_type_id = next((v for v in all_types if v not in {"Attribute", "Type", "Relation", "RelationType"}), None)
                type_name = self.rel_id_to_name.get(relation_type_id, "unknown")
                self.relationships.append({
                    "entity_id": entity_id,
                    "from": from_entity,
                    "to": to_entity,
                    "type": relation_type_id,
                    "type_name": type_name,
                })
            else:
                self.node_ids.add(entity_id)
        
        self.stats["nodes"] = len(self.node_ids)
        self.stats["relations"] = len(self.relation_ids)
        print(f"  ✅ Nodes: {self.stats['nodes']:,}")
        print(f"  ✅ Relations: {self.stats['relations']:,}")
        
    def create_pubchem_provenance(self):
        pubchem_file = DATA_DIR / "pubchem_properties.json"
        if not pubchem_file.exists():
            return None
        
        with open(pubchem_file, 'r') as f:
            data = json.load(f)
        
        prov_id = data.get("provenance_entity")
        pubchem_dates = data.get("pubchem_dates", {})
        
        if not prov_id:
            return None
        
        files = [f"{k}: {v}" for k, v in pubchem_dates.items()]
        citation = f"PubChem properties from {', '.join(files)}"
        date = max(pubchem_dates.values()) if pubchem_dates else None
        
        provenance = {
            "entity": prov_id,
            "triples": [
                {"entity": prov_id, "attribute": GRC20_TYPE, "value": {"type": 1, "value": self.schema.types["Provenance"]}},
                {"entity": prov_id, "attribute": self.schema.attr("name"), "value": {"type": 1, "value": f"PubChem - {date}"}},
                {"entity": prov_id, "attribute": self.schema.attr("source"), "value": {"type": 1, "value": "PubChem"}},
                {"entity": prov_id, "attribute": self.schema.attr("citation"), "value": {"type": 1, "value": citation}},
                {"entity": prov_id, "attribute": self.schema.attr("date_accessed"), "value": {"type": 1, "value": date or "unknown"}},
                {"entity": prov_id, "attribute": self.schema.attr("source_url"), "value": {"type": 1, "value": "https://pubchem.ncbi.nlm.nih.gov"}},
                {"entity": prov_id, "attribute": self.schema.attr("provenance_type"), "value": {"type": 1, "value": "IMPORTED"}},
            ]
        }
        return provenance

    def create_pipeline_provenance(self):
        """Create a provenance entity for system-generated data."""
        # Use a deterministic ID based on the Schema if possible, or a fixed one
        # For consistency, let's use a standard UUID for this pipeline
        prov_id = "Vi38GjMNzRSCtLHHdAQWbH" # Matches the ID from previous fix attempts
        
        provenance = {
            "entity": prov_id,
            "triples": [
                {"entity": prov_id, "attribute": GRC20_TYPE, "value": {"type": 1, "value": self.schema.types["Provenance"]}},
                {"entity": prov_id, "attribute": self.schema.attr("name"), "value": {"type": 1, "value": "Pipeline Generated"}},
                {"entity": prov_id, "attribute": self.schema.attr("source"), "value": {"type": 1, "value": "pipeline_generated"}},
                {"entity": prov_id, "attribute": self.schema.attr("citation"), "value": {"type": 1, "value": "Generated by GRC-20 Pharmaceutical Knowledge Graph Pipeline"}},
                {"entity": prov_id, "attribute": self.schema.attr("date_accessed"), "value": {"type": 1, "value": datetime.now().strftime("%Y-%m-%d")}},
                {"entity": prov_id, "attribute": self.schema.attr("source_url"), "value": {"type": 1, "value": "https://github.com/geo-knowledge-graph/pharma-pipeline"}},
                {"entity": prov_id, "attribute": self.schema.attr("provenance_type"), "value": {"type": 1, "value": "GENERATED"}},
            ]
        }
        return provenance

    def export(self, filepath: Path):
        print("\n" + "=" * 70)
        print("EXPORTING")
        print("=" * 70)
        
        rel_type_counts = defaultdict(int)
        for rel in self.relationships:
            rel_type_counts[rel["type_name"]] += 1
        
        output = {
            "space": "pharma",
            "version": "2.0.0",
            "exported_at": datetime.now().isoformat(),
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
            "entities": list(self.entities.values()),
            "node_ids": list(self.node_ids),
            "relation_ids": list(self.relation_ids),
            "relationships": self.relationships,
        }
        
        # Add Provenance Entities
        added_prov = False
        
        pubchem_prov = self.create_pubchem_provenance()
        if pubchem_prov:
            output["entities"].append(pubchem_prov)
            print(f"  ✅ Added PubChem provenance: {pubchem_prov['entity']}")
            added_prov = True

        pipeline_prov = self.create_pipeline_provenance()
        if pipeline_prov:
            # Only add if not already present (e.g. from RxNorm)
            if not any(e['entity'] == pipeline_prov['entity'] for e in output['entities']):
                output["entities"].append(pipeline_prov)
                print(f"  ✅ Added Pipeline provenance: {pipeline_prov['entity']}")
                added_prov = True
        
        if added_prov:
            print("  ✅ All Provenance Entities Exported")
        
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)
        
        size_mb = filepath.stat().st_size / 1024 / 1024
        print(f"  ✅ Exported to: {filepath} ({size_mb:.1f} MB)")

def main():
    parser = argparse.ArgumentParser(description="Merge GRC-20 files and enrich")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output file path")
    args = parser.parse_args()
    merger = GRC20Merger()
    merger.merge_all()
    merger.export(args.output)

if __name__ == "__main__":
    main()
