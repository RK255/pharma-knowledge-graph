"""
Provenance Manager for GRC-20 Pipeline
Ensures all entities have provenance tracking.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Import schema for attribute IDs
import sys
sys.path.insert(0, str(Path(__file__).parent / "00_schema"))
from pharma_schema import PharmaSchema, GRC20_SYSTEM_TYPES


class ProvenanceManager:
    """Manages provenance entities and coverage validation."""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent
        self.schema = PharmaSchema()
        self.provenance_entities: Dict[str, dict] = {}
        
        # Attribute IDs from schema
        self.attr_provenance = self.schema.attr("provenance")
        self.attr_name = self.schema.attr("name")
        self.attr_source = self.schema.attr("source")
        self.attr_citation = self.schema.attr("citation")
        self.attr_date_accessed = self.schema.attr("date_accessed")
        self.attr_provenance_type = self.schema.attr("provenance_type")
        self.attr_type = self.schema.attr("type")
        
        # Type IDs
        self.type_provenance = self.schema.types.get("Provenance")
        
        # GRC-20 System Types (meta-types for schema definitions)
        self.meta_types = [
            GRC20_SYSTEM_TYPES['Type'],
            GRC20_SYSTEM_TYPES['Attribute'],
            GRC20_SYSTEM_TYPES['Relation'],
            GRC20_SYSTEM_TYPES['RelationType'],
        ]
    
    def load_data(self, filepath: str) -> dict:
        """Load full JSON data structure."""
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def load_entities(self, filepath: str) -> List[dict]:
        """Load entities array from JSON file."""
        data = self.load_data(filepath)
        return data.get("entities", [])
    
    def save_data(self, data: dict, filepath: str):
        """Save full JSON data structure."""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _get_entity_type_id(self, entity: dict) -> Optional[str]:
        """Get the type ID of an entity."""
        for triple in entity.get("triples", []):
            if triple.get("attribute") == self.attr_type:
                value = triple.get("value", {})
                if isinstance(value, dict):
                    return value.get("value")
                return value
        return None
    
    def get_coverage_stats(self, entities: List[dict]) -> Dict[str, Any]:
        """Calculate provenance coverage statistics."""
        total = len(entities)
        with_provenance = 0
        without_provenance = []
        skipped_types = {"meta": 0, "provenance": 0}
        
        for entity in entities:
            entity_id = entity.get("entity", "")
            entity_type = self._get_entity_type_id(entity)
            
            # Skip type definition entities (meta-types for schema)
            if entity_type in self.meta_types:
                skipped_types["meta"] += 1
                with_provenance += 1
                continue
            
            # Skip Provenance entities (they ARE provenance, don't need it)
            if entity_type == self.type_provenance:
                skipped_types["provenance"] += 1
                with_provenance += 1
                continue
            
            # Check for provenance triple
            has_prov = False
            for triple in entity.get("triples", []):
                attr = triple.get("attribute", "")
                if attr == self.attr_provenance:
                    has_prov = True
                    break
            
            if has_prov:
                with_provenance += 1
            else:
                without_provenance.append(entity_id)
        
        coverage = (with_provenance / total * 100) if total > 0 else 100
        
        return {
            "total": total,
            "with_provenance": with_provenance,
            "without_provenance": len(without_provenance),
            "coverage": coverage,
            "missing_ids": without_provenance[:10],
            "skipped": skipped_types
        }
    
    def _is_type_definition(self, entity: dict) -> bool:
        """Check if entity is a type/attribute/relation definition."""
        entity_type = self._get_entity_type_id(entity)
        return entity_type in self.meta_types
    
    def _is_provenance_entity(self, entity: dict) -> bool:
        """Check if entity IS a provenance entity."""
        entity_type = self._get_entity_type_id(entity)
        return entity_type == self.type_provenance
    
    def _make_value(self, value: Any, value_type: int = 1) -> dict:
        """Create a GRC-20 value object."""
        return {"type": value_type, "value": value}
    
    def create_provenance(
        self,
        source: str,
        citation: str,
        date_accessed: str,
        provenance_type: str = "DATASET",
        provenance_id: Optional[str] = None
    ) -> dict:
        """Create a provenance entity in GRC-20 format."""
        if provenance_id is None:
            provenance_id = self.schema.generate_id()
        
        triples = [
            {
                "entity": provenance_id,
                "attribute": self.attr_type,
                "value": self._make_value(self.type_provenance)
            },
            {
                "entity": provenance_id,
                "attribute": self.attr_name,
                "value": self._make_value(source)
            },
            {
                "entity": provenance_id,
                "attribute": self.attr_source,
                "value": self._make_value(source)
            },
            {
                "entity": provenance_id,
                "attribute": self.attr_citation,
                "value": self._make_value(citation)
            },
            {
                "entity": provenance_id,
                "attribute": self.attr_date_accessed,
                "value": self._make_value(date_accessed, value_type=5)
            },
            {
                "entity": provenance_id,
                "attribute": self.attr_provenance_type,
                "value": self._make_value(provenance_type)
            },
        ]
        
        provenance = {
            "space": "pharma",
            "entity": provenance_id,
            "triples": triples
        }
        
        self.provenance_entities[source] = provenance
        return provenance
    
    def add_provenance_to_entities(
        self,
        entities: List[dict],
        provenance_id: str
    ) -> List[dict]:
        """Add provenance triple to entities that don't have it."""
        updated = 0
        
        for entity in entities:
            # Skip type definitions and provenance entities
            if self._is_type_definition(entity) or self._is_provenance_entity(entity):
                continue
            
            # Check if already has provenance
            has_prov = any(
                t.get("attribute") == self.attr_provenance
                for t in entity.get("triples", [])
            )
            
            if not has_prov:
                entity["triples"].append({
                    "entity": entity.get("entity"),
                    "attribute": self.attr_provenance,
                    "value": self._make_value(provenance_id)
                })
                updated += 1
        
        print(f"  Added provenance to {updated} entities")
        return entities


def main():
    """CLI entry point for provenance management."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Provenance Manager")
    parser.add_argument("--input", required=True, help="Input entities JSON file")
    parser.add_argument("--output", help="Output file (default: overwrite input)")
    parser.add_argument("--check", action="store_true", help="Check coverage only")
    parser.add_argument("--fix", action="store_true", help="Add missing provenance")
    
    args = parser.parse_args()
    
    pm = ProvenanceManager()
    
    # Load full data structure
    data = pm.load_data(args.input)
    entities = data.get("entities", [])
    stats = pm.get_coverage_stats(entities)
    
    print(f"\n{'='*60}")
    print("PROVENANCE COVERAGE REPORT")
    print(f"{'='*60}")
    print(f"  Total entities: {stats['total']:,}")
    print(f"  With provenance: {stats['with_provenance']:,}")
    print(f"  Without provenance: {stats['without_provenance']:,}")
    print(f"  Skipped meta-types: {stats['skipped']['meta']}")
    print(f"  Skipped provenance entities: {stats['skipped']['provenance']}")
    print(f"  Coverage: {stats['coverage']:.1f}%")
    
    if stats['missing_ids']:
        print(f"\n  Sample missing IDs: {stats['missing_ids'][:5]}")
    
    if args.fix and stats['coverage'] < 100:
        # Create pipeline_generated provenance
        prov = pm.create_provenance(
            source="pipeline_generated",
            citation="Generated by pharma knowledge graph pipeline",
            date_accessed=datetime.now().strftime("%Y-%m-%d"),
            provenance_type="GENERATED"
        )
        
        # Update entities
        data["entities"] = pm.add_provenance_to_entities(entities, prov["id"])
        
        # Add provenance entity to the list
        data["entities"].append(prov)
        
        # Update stats
        if "stats" in data:
            data["stats"]["provenance_added"] = stats['without_provenance']
        
        # Save
        output = args.output or args.input
        pm.save_data(data, output)
        print(f"\n  Saved to: {output}")
    
    print(f"{'='*60}\n")
    
    return stats['coverage'] == 100


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
