#!/usr/bin/env python3
"""
Convert all staging files to GRC-20 format

FIXED: Now uses proper "provenance" attribute instead of "has_provenance" relation type
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pharma_schema import PharmaSchema, generate_grc20_id

class GRC20StagingConverter:
    """Convert staging files to GRC-20 format."""
    
    def __init__(self):
        self.schema = PharmaSchema()
        self.data_dir = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop/data")
        self.staging_dir = self.data_dir / "grc20_staging"
        self.output_file = self.data_dir / "grc20_merged.json"
        self.provenance_attr_id = self.schema.attr("provenance")
        
    def create_provenance(self, source: str, citation: str, source_url: str = None) -> str:
        """Create a provenance entity."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        entity = self.schema.create_provenance(
            source=source,
            citation=citation,
            date_accessed=date_str,
            source_url=source_url,
            provenance_type="IMPORTED",
        )
        
        return entity["entity"]
    
    def process_rxnorm(self) -> List[dict]:
        """Process RxNorm staging file."""
        print("Processing RxNorm staging file...")
        
        staging_file = self.staging_dir / "rxnorm_grc20.json"
        
        if not staging_file.exists():
            print(f"  WARNING: {staging_file} not found, skipping")
            return []
        
        with open(staging_file, 'r') as f:
            data = json.load(f)
        
        # Get provenance from staging file
        prov_id = data.get("provenance_entity")
        if not prov_id:
            prov_id = self.create_provenance(
                source="RxNorm",
                citation="RxNorm, National Library of Medicine",
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
                source_url="https://rxnav.nlm.nih.gov/",
            )
        
        entities = data.get('entities', [])
        
        # Add provenance link to all entities that don't have it
        updated_entities = []
        for entity in entities:
            entity_id = entity.get('entity', '')
            has_provenance = False
            
            for triple in entity.get('triples', []):
                if triple.get('attribute') == self.provenance_attr_id:
                    has_provenance = True
                    break
            
            if not has_provenance:
                entity_copy = {
                    "entity": entity_id,
                    "triples": entity.get('triples', []).copy()
                }
                entity_copy['triples'].append({
                    "entity": entity_id,
                    "attribute": self.provenance_attr_id,  # FIXED: Using provenance attribute
                    "value": {"type": 1, "value": prov_id}
                })
                updated_entities.append(entity_copy)
            else:
                updated_entities.append(entity)
        
        print(f"  Processed {len(updated_entities)} entities")
        return updated_entities
    
    def process_ndc_bridge(self) -> List[dict]:
        """Process NDC Bridge staging file."""
        print("Processing NDC Bridge staging file...")
        
        staging_file = self.staging_dir / "ndc_bridge_grc20.json"
        
        if not staging_file.exists():
            print(f"  WARNING: {staging_file} not found, skipping")
            return []
        
        with open(staging_file, 'r') as f:
            data = json.load(f)
        
        # Get provenance from staging file
        prov_id = data.get("provenance_entity")
        if not prov_id:
            prov_id = self.create_provenance(
                source="FDA NDC Directory",
                citation="FDA National Drug Code Directory",
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
                source_url="https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory",
            )
        
        entities = data.get('entities', [])
        
        # Add provenance link to all entities that don't have it
        updated_entities = []
        for entity in entities:
            entity_id = entity.get('entity', '')
            has_provenance = False
            
            for triple in entity.get('triples', []):
                if triple.get('attribute') == self.provenance_attr_id:
                    has_provenance = True
                    break
            
            if not has_provenance:
                entity_copy = {
                    "entity": entity_id,
                    "triples": entity.get('triples', []).copy()
                }
                entity_copy['triples'].append({
                    "entity": entity_id,
                    "attribute": self.provenance_attr_id,  # FIXED: Using provenance attribute
                    "value": {"type": 1, "value": prov_id}
                })
                updated_entities.append(entity_copy)
            else:
                updated_entities.append(entity)
        
        print(f"  Processed {len(updated_entities)} entities")
        return updated_entities
    
    def process_pubchem(self) -> List[dict]:
        """Process PubChem staging file."""
        print("Processing PubChem staging file...")
        
        staging_file = self.staging_dir / "pubchem_grc20.json"
        
        if not staging_file.exists():
            print(f"  WARNING: {staging_file} not found, skipping")
            return []
        
        with open(staging_file, 'r') as f:
            data = json.load(f)
        
        # Get provenance from staging file
        prov_id = data.get("provenance_entity")
        if not prov_id:
            prov_id = self.create_provenance(
                source="PubChem",
                citation="PubChem Compound Database, NCBI",
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
                source_url="https://pubchem.ncbi.nlm.nih.gov/",
            )
        
        entities = data.get('entities', [])
        
        # Add provenance link to all entities that don't have it
        updated_entities = []
        for entity in entities:
            entity_id = entity.get('entity', '')
            has_provenance = False
            
            for triple in entity.get('triples', []):
                if triple.get('attribute') == self.provenance_attr_id:
                    has_provenance = True
                    break
            
            if not has_provenance:
                entity_copy = {
                    "entity": entity_id,
                    "triples": entity.get('triples', []).copy()
                }
                entity_copy['triples'].append({
                    "entity": entity_id,
                    "attribute": self.provenance_attr_id,  # FIXED: Using provenance attribute
                    "value": {"type": 1, "value": prov_id}
                })
                updated_entities.append(entity_copy)
            else:
                updated_entities.append(entity)
        
        print(f"  Processed {len(updated_entities)} entities")
        return updated_entities
    
    def run(self):
        """Run the staging conversion process."""
        print("=" * 80)
        print("GRC-20 STAGING CONVERTER (FIXED)")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Staging dir: {self.staging_dir}")
        print(f"Output: {self.output_file}")
        print("=" * 80)
        
        all_entities = []
        
        # Process all staging files
        all_entities.extend(self.process_rxnorm())
        all_entities.extend(self.process_ndc_bridge())
        all_entities.extend(self.process_pubchem())
        
        # Save merged output
        print(f"Saving merged output to {self.output_file}...")
        output_data = {
            "entities": all_entities,
            "metadata": {
                "merged": datetime.now().isoformat(),
                "schema_version": self.schema.metadata.get("version", "2.0.0"),
                "total_entities": len(all_entities),
            }
        }
        
        with open(self.output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print("=" * 80)
        print("CONVERSION COMPLETE")
        print("=" * 80)
        print(f"  Total entities: {len(all_entities):,}")
        print(f"  Output file: {self.output_file}")
        print("=" * 80)

if __name__ == "__main__":
    converter = GRC20StagingConverter()
    converter.run()
