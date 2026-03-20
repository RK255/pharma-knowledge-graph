"""
Provenance Manager for GRC-20 Pipeline (v2)
Ensures all entities have provenance tracking via has_provenance relations.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent / "00_schema"))
from pharma_schema import PharmaSchema, PROVENANCE_SOURCES, generate_uuid


class ProvenanceManager:
    """Manages provenance entities and coverage validation for GRC-20 format."""
    
    # GRC-20 standard IDs
    HAS_PROVENANCE_REL_ID = "40336b51fbf358408ee0cbcc808d43b6"
    PROVENANCE_TYPE_ID = "bf18230767f55134938b218f276a8582"
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent.parent / "data" / "grc20_v2"
        self.schema = PharmaSchema()
        
        # Property IDs
        self.prop_name = self.schema.prop("name")
        self.prop_source = self.schema.prop("source")
        self.prop_citation = self.schema.prop("citation")
        self.prop_date_accessed = self.schema.prop("date_accessed")
        self.prop_source_url = self.schema.prop("source_url")
        self.prop_provenance_type = self.schema.prop("provenance_type")
        
        # Track provenance entities
        self.provenance_entities: Dict[str, dict] = {}
    
    def load_entities_jsonl(self, filepath: str) -> List[dict]:
        """Load entities from JSONL file."""
        entities = []
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    entities.append(json.loads(line))
        return entities
    
    def load_relations_jsonl(self, filepath: str) -> List[dict]:
        """Load relations from JSONL file."""
        relations = []
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    relations.append(json.loads(line))
        return relations
    
    def save_entities_jsonl(self, entities: List[dict], filepath: str):
        """Save entities to JSONL file."""
        with open(filepath, 'w') as f:
            for entity in entities:
                f.write(json.dumps(entity) + '\n')
    
    def save_relations_jsonl(self, relations: List[dict], filepath: str):
        """Save relations to JSONL file."""
        with open(filepath, 'w') as f:
            for rel in relations:
                f.write(json.dumps(rel) + '\n')
    
    def _is_provenance_entity(self, entity: dict) -> bool:
        """Check if entity IS a provenance entity."""
        return self.PROVENANCE_TYPE_ID in entity.get('types', [])
    
    def get_coverage_stats(self, entities: List[dict], relations: List[dict]) -> Dict[str, Any]:
        """Calculate provenance coverage statistics."""
        # Find provenance entities
        provenance_ids = set()
        for entity in entities:
            if self._is_provenance_entity(entity):
                provenance_ids.add(entity['id'])
                self.provenance_entities[entity.get('name', entity['id'])] = entity
        
        # Find entities with provenance relations
        entities_with_prov = set()
        for rel in relations:
            if rel.get('type') == self.HAS_PROVENANCE_REL_ID:
                entities_with_prov.add(rel.get('from'))
        
        # Count non-provenance entities
        non_prov_entities = [e for e in entities if not self._is_provenance_entity(e)]
        total_non_prov = len(non_prov_entities)
        
        # Count entities without provenance
        without_provenance = [e for e in non_prov_entities if e['id'] not in entities_with_prov]
        
        coverage = (len(entities_with_prov) / total_non_prov * 100) if total_non_prov > 0 else 100
        
        return {
            "total_entities": len(entities),
            "provenance_entities": len(provenance_ids),
            "non_provenance_entities": total_non_prov,
            "with_provenance": len(entities_with_prov),
            "without_provenance": len(without_provenance),
            "coverage": coverage,
            "missing_ids": [e['id'] for e in without_provenance[:10]]
        }
    
    def create_provenance_entity(
        self,
        source: str,
        citation: str,
        date_accessed: str,
        source_url: str = "",
        provenance_type: str = "GENERATED",
        provenance_id: Optional[str] = None
    ) -> dict:
        """Create a provenance entity in GRC-20 format."""
        if provenance_id is None:
            provenance_id = generate_uuid(seed=f"prov_{source}")
        
        values = [
            {"property": self.prop_name, "value": source},
            {"property": self.prop_source, "value": source},
            {"property": self.prop_citation, "value": citation},
            {"property": self.prop_date_accessed, "value": date_accessed},
            {"property": self.prop_provenance_type, "value": provenance_type},
        ]
        
        if source_url:
            values.append({"property": self.prop_source_url, "value": source_url})
        
        return {
            "id": provenance_id,
            "name": source,
            "types": [self.PROVENANCE_TYPE_ID],
            "values": values
        }
    
    def create_provenance_relation(self, entity_id: str, provenance_id: str) -> dict:
        """Create a has_provenance relation."""
        return {
            "id": generate_uuid(seed=f"prov_rel_{entity_id}_{provenance_id}"),
            "type": self.HAS_PROVENANCE_REL_ID,
            "from": entity_id,
            "to": provenance_id,
            "values": []
        }
    
    def add_provenance_to_entities(
        self,
        entities: List[dict],
        relations: List[dict],
        provenance_id: str
    ) -> tuple:
        """Add provenance relations to entities that don't have them."""
        # Find existing provenance relations
        entities_with_prov = set()
        for rel in relations:
            if rel.get('type') == self.HAS_PROVENANCE_REL_ID:
                entities_with_prov.add(rel.get('from'))
        
        # Add provenance relations for entities without
        added = 0
        for entity in entities:
            # Skip provenance entities
            if self._is_provenance_entity(entity):
                continue
            
            if entity['id'] not in entities_with_prov:
                rel = self.create_provenance_relation(entity['id'], provenance_id)
                relations.append(rel)
                added += 1
        
        return entities, relations, added


def main():
    """CLI entry point for provenance management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Provenance Manager v2")
    parser.add_argument("--entities", required=True, help="Input entities JSONL file")
    parser.add_argument("--relations", required=True, help="Input relations JSONL file")
    parser.add_argument("--fix", action="store_true", help="Add missing provenance")
    
    args = parser.parse_args()
    
    pm = ProvenanceManager()
    
    # Load data
    print("Loading data...")
    entities = pm.load_entities_jsonl(args.entities)
    relations = pm.load_relations_jsonl(args.relations)
    
    # Get stats
    stats = pm.get_coverage_stats(entities, relations)
    
    print(f"\n{'='*60}")
    print("PROVENANCE COVERAGE REPORT")
    print(f"{'='*60}")
    print(f"  Total entities: {stats['total_entities']:,}")
    print(f"  Provenance entities: {stats['provenance_entities']}")
    print(f"  Non-provenance entities: {stats['non_provenance_entities']:,}")
    print(f"  With provenance: {stats['with_provenance']:,}")
    print(f"  Without provenance: {stats['without_provenance']:,}")
    print(f"  Coverage: {stats['coverage']:.1f}%")
    
    if stats['missing_ids']:
        print(f"\n  Sample missing IDs: {stats['missing_ids'][:5]}")
    
    if args.fix and stats['coverage'] < 100:
        # Create pipeline_generated provenance
        prov = pm.create_provenance_entity(
            source="pipeline_generated",
            citation="Generated by pharma knowledge graph pipeline",
            date_accessed=datetime.now().strftime("%Y-%m-%d"),
            provenance_type="GENERATED"
        )
        
        entities.append(prov)
        entities, relations, added = pm.add_provenance_to_entities(
            entities, relations, prov['id']
        )
        
        print(f"\n  Added provenance to {added} entities")
        
        # Save
        pm.save_entities_jsonl(entities, args.entities)
        pm.save_relations_jsonl(relations, args.relations)
        print(f"  Saved to: {args.entities}")
        print(f"  Saved to: {args.relations}")
        
        stats = pm.get_coverage_stats(entities, relations)
        print(f"\n  New coverage: {stats['coverage']:.1f}%")
    
    print(f"{'='*60}\n")
    
    return stats['coverage'] == 100


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
