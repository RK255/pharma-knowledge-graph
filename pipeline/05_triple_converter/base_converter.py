#!/usr/bin/env python3
"""
GRC-20 Base Converter
=====================

Base class for all GRC-20 converters. Provides:
- Unified schema access
- Provenance management
- Entity/relation creation
- Export to standard format

All pipeline converters should inherit from this class.

Usage:
    from base_converter import GRC20BaseConverter
    
    class MyConverter(GRC20BaseConverter):
        def convert(self):
            prov_id = self.create_provenance("MySource", "Citation...")
            entity_id = self.create_entity("Drug", "Aspirin", provenance_id=prov_id)
            self.export("my_output.json")
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add schema to path
sys.path.insert(0, str(Path(__file__).parent.parent / "00_schema"))
from pharma_schema import PharmaSchema, generate_grc20_id, GRC20_STANDARD_ATTRIBUTES, GRC20_RELATION_ATTRIBUTES


class GRC20BaseConverter:
    """
    Base class for GRC-20 converters.
    
    Provides:
    - Unified schema access
    - Provenance registry (deduplicates provenance entities)
    - Entity creation with automatic provenance linking
    - Relation creation
    - Export to standard GRC-20 format
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize converter.
        
        Args:
            output_dir: Directory for output files (default: data/grc20_v2/)
        """
        self.schema = PharmaSchema()
        
        # Output directory
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "grc20_v2"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Provenance registry (deduplicates by source+citation+date)
        self.provenance_registry: Dict[str, str] = {}  # key -> entity_id
        self.provenance_entities: List[Dict] = []
        
        # Entity storage
        self.entities: List[Dict] = []
        self.relations: List[Dict] = []
        
        # Lookup indexes
        self.entity_by_external_id: Dict[str, str] = {}  # external_id -> grc20_id
        self.entity_by_name: Dict[str, str] = {}  # name -> grc20_id (for unique names)
        
        # Statistics
        self.stats = {
            "entities_created": 0,
            "relations_created": 0,
            "provenance_created": 0,
            "skipped_duplicates": 0,
        }
    
    # =========================================================================
    # PROVENANCE
    # =========================================================================
    
    def create_provenance(
        self,
        source: str,
        citation: str,
        date_accessed: str,
        date_published: Optional[str] = None,
        source_url: Optional[str] = None,
        source_file: Optional[str] = None,
        curator_name: Optional[str] = None,
        curator_credentials: Optional[str] = None,
        provenance_type: str = "AUTOMATED",
    ) -> str:
        """
        Create or retrieve a provenance entity.
        
        Provenance is deduplicated by (source, citation, date_accessed, curator_name).
        If the same provenance already exists, returns existing ID.
        
        Args:
            source: Data source name (RxNorm, PubChem, FDA-SPL, etc.)
            citation: AMA-formatted citation
            date_accessed: Date data was accessed (YYYY-MM-DD)
            date_published: Date source was published
            source_url: URL to data source
            source_file: Source file name
            curator_name: Expert curator name (for EXPERT_CURATED)
            curator_credentials: Curator credentials (PharmD, MD, etc.)
            provenance_type: AUTOMATED, EXPERT_CURATED, or INFERRED
            
        Returns:
            Provenance entity ID
        """
        # Create deduplication key
        key = f"{source}|{citation}|{date_accessed}|{curator_name or 'auto'}"
        
        if key in self.provenance_registry:
            return self.provenance_registry[key]
        
        # Create provenance entity
        props = {
            "source": source,
            "citation": citation,
            "date_accessed": date_accessed,
            "provenance_type": provenance_type,
        }
        
        if date_published:
            props["date_published"] = date_published
        if source_url:
            props["source_url"] = source_url
        if source_file:
            props["source_file"] = source_file
        if curator_name:
            props["curator_name"] = curator_name
        if curator_credentials:
            props["curator_credentials"] = curator_credentials
        
        entity = self.schema.create_entity(
            entity_type="Provenance",
            name=f"{source} - {date_accessed}",
            **props
        )
        
        self.provenance_registry[key] = entity["entity"]
        self.provenance_entities.append(entity)
        self.stats["provenance_created"] += 1
        
        return entity["entity"]
    
    # =========================================================================
    # ENTITIES
    # =========================================================================
    
    def create_entity(
        self,
        entity_type: str,
        name: str,
        external_id: Optional[str] = None,
        provenance_id: Optional[str] = None,
        **properties,
    ) -> str:
        """
        Create an entity with optional provenance.
        
        Args:
            entity_type: Type (Drug, Ingredient, ClinicalDrug, etc.)
            name: Entity name
            external_id: External ID for lookup (e.g., "rxcui:29046")
            provenance_id: Provenance entity ID
            **properties: Additional properties (rxcui, ndc_code, smiles, etc.)
            
        Returns:
            Entity ID
        """
        entity = self.schema.create_entity(
            entity_type=entity_type,
            name=name,
            **properties
        )
        entity_id = entity["entity"]
        
        # Add provenance relation
        if provenance_id:
            entity["triples"].append({
                "entity": entity_id,
                "attribute": self.schema.rel("has_provenance"),
                "value": {"type": 1, "value": provenance_id},
            })
        
        self.entities.append(entity)
        self.stats["entities_created"] += 1
        
        # Index by external ID
        if external_id:
            self.entity_by_external_id[external_id] = entity_id
        
        return entity_id
    
    def create_drug(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create a Drug entity."""
        return self.create_entity("Drug", name, provenance_id=provenance_id, **props)
    
    def create_ingredient(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create an Ingredient entity."""
        return self.create_entity("Ingredient", name, provenance_id=provenance_id, **props)
    
    def create_clinical_drug(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create a ClinicalDrug entity (RxNorm SCD)."""
        return self.create_entity("ClinicalDrug", name, provenance_id=provenance_id, **props)
    
    def create_branded_drug(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create a BrandedDrug entity (RxNorm SBD)."""
        return self.create_entity("BrandedDrug", name, provenance_id=provenance_id, **props)
    
    def create_brand_name(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create a BrandName entity."""
        return self.create_entity("BrandName", name, provenance_id=provenance_id, **props)
    
    def create_dose_form(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create a DoseForm entity."""
        return self.create_entity("DoseForm", name, provenance_id=provenance_id, **props)
    
    def create_ndc(self, ndc_code: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create an NDC entity."""
        return self.create_entity("NDC", ndc_code, provenance_id=provenance_id, ndc_code=ndc_code, **props)
    
    def create_package_insert(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create a PackageInsert entity."""
        return self.create_entity("PackageInsert", name, provenance_id=provenance_id, **props)
    
    def create_pharmacological_class(self, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """Create a PharmacologicalClass entity."""
        return self.create_entity("PharmacologicalClass", name, provenance_id=provenance_id, **props)
    
    # =========================================================================
    # RELATIONS
    # =========================================================================
    
    def add_relation(
        self,
        from_entity: str,
        relation_type: str,
        to_entity: str,
    ) -> str:
        """
        Add a relation between two entities.
        
        Args:
            from_entity: Source entity ID
            relation_type: Relation type (has_ingredient, has_dose_form, etc.)
            to_entity: Target entity ID
            
        Returns:
            Relation entity ID
        """
        relation_triples = self.schema.relation(
            from_entity=from_entity,
            relation_type=relation_type,
            to_entity=to_entity,
        )
        
        relation_id = relation_triples[0]["entity"]
        
        self.relations.append({
            "space": "pharma",
            "entity": relation_id,
            "triples": relation_triples,
        })
        
        self.stats["relations_created"] += 1
        
        return relation_id
    
    def get_or_create_entity(self, entity_type: str, name: str, provenance_id: Optional[str] = None, **props) -> str:
        """
        Get existing entity by name or create new one.
        
        Useful for entities like DoseForm that may be referenced multiple times.
        """
        if name in self.entity_by_name:
            return self.entity_by_name[name]
        
        entity_id = self.create_entity(entity_type, name, provenance_id=provenance_id, **props)
        self.entity_by_name[name] = entity_id
        return entity_id
    
    # =========================================================================
    # LOOKUP
    # =========================================================================
    
    def get_entity_by_external_id(self, external_id: str) -> Optional[str]:
        """Look up entity by external ID (e.g., 'rxcui:29046')."""
        return self.entity_by_external_id.get(external_id)
    
    def get_entity_by_name(self, name: str) -> Optional[str]:
        """Look up entity by name."""
        return self.entity_by_name.get(name)
    
    # =========================================================================
    # EXPORT
    # =========================================================================
    
    def export(self, filename: str, include_stats: bool = True) -> Dict:
        """
        Export all entities to a GRC-20 JSON file.
        
        Args:
            filename: Output filename (will be saved to output_dir)
            include_stats: Include statistics in output
            
        Returns:
            Export statistics
        """
        all_entities = (
            self.provenance_entities +
            self.entities +
            self.relations
        )
        
        output = {
            "space": "pharma",
            "version": "2.0.0",
            "exported_at": datetime.now().isoformat(),
            "schema_version": self.schema.metadata.get("version", "1.0.0"),
            "stats": {
                "total_entities": len(all_entities),
                "provenance_entities": len(self.provenance_entities),
                "data_entities": len(self.entities),
                "relations": len(self.relations),
            },
            "entities": all_entities,
        }
        
        output_path = self.output_dir / filename
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        
        if include_stats:
            print(f"Exported to: {output_path}")
            print(f"  Provenance: {output['stats']['provenance_entities']}")
            print(f"  Entities: {output['stats']['data_entities']}")
            print(f"  Relations: {output['stats']['relations']}")
            print(f"  Total: {output['stats']['total_entities']}")
        
        return output["stats"]
    
    def merge_export(self, other_converter: 'GRC20BaseConverter', filename: str) -> Dict:
        """
        Merge this converter's data with another and export.
        
        Useful for combining multiple pipeline outputs.
        """
        # Merge provenance registries
        for key, prov_id in other_converter.provenance_registry.items():
            if key not in self.provenance_registry:
                self.provenance_registry[key] = prov_id
        
        # Merge provenance entities
        existing_prov_ids = {e["entity"] for e in self.provenance_entities}
        for prov in other_converter.provenance_entities:
            if prov["entity"] not in existing_prov_ids:
                self.provenance_entities.append(prov)
        
        # Merge entities
        self.entities.extend(other_converter.entities)
        
        # Merge relations
        self.relations.extend(other_converter.relations)
        
        # Merge indexes
        self.entity_by_external_id.update(other_converter.entity_by_external_id)
        self.entity_by_name.update(other_converter.entity_by_name)
        
        # Update stats
        self.stats["entities_created"] += other_converter.stats["entities_created"]
        self.stats["relations_created"] += other_converter.stats["relations_created"]
        self.stats["provenance_created"] += other_converter.stats["provenance_created"]
        
        return self.export(filename)
    
    # =========================================================================
    # UTILITY
    # =========================================================================
    
    def add_property(self, entity_id: str, attribute: str, value: Any, value_type: Optional[int] = None) -> None:
        """
        Add a property triple to an existing entity.
        
        Args:
            entity_id: Entity ID
            attribute: Attribute name (will be resolved via schema)
            value: Property value
            value_type: Optional value type override
        """
        triple = self.schema.triple(entity_id, attribute, value, value_type)
        
        # Find the entity and add the triple
        for entity in self.entities:
            if entity["entity"] == entity_id:
                entity["triples"].append(triple)
                return
        
        # Also check provenance entities
        for entity in self.provenance_entities:
            if entity["entity"] == entity_id:
                entity["triples"].append(triple)
                return
    
    def summary(self) -> str:
        """Return a summary of the converter state."""
        return f"""
GRC-20 Converter Summary
========================
Provenance entities: {len(self.provenance_entities)}
Data entities:       {len(self.entities)}
Relations:           {len(self.relations)}
Total:               {len(self.provenance_entities) + len(self.entities) + len(self.relations)}

Stats:
  Entities created:  {self.stats['entities_created']}
  Relations created: {self.stats['relations_created']}
  Provenance created: {self.stats['provenance_created']}
  Duplicates skipped: {self.stats['skipped_duplicates']}
"""


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    # Demo usage
    converter = GRC20BaseConverter()
    
    # Create provenance
    prov = converter.create_provenance(
        source="Test",
        citation="Test citation",
        date_accessed="2026-02-26",
    )
    
    # Create entities
    drug = converter.create_drug("Test Drug", provenance_id=prov, rxcui="12345")
    ing = converter.create_ingredient("Test Ingredient", provenance_id=prov)
    
    # Create relation
    converter.add_relation(drug, "has_ingredient", ing)
    
    # Export
    print(converter.summary())
    converter.export("test_output.json")
