#!/usr/bin/env python3
"""
GRC-20 Triple Converter
=======================

Converts staging JSONs to GRC-20 triple format for Neo4j loading.

Input staging files:
- rxnorm_entities.json - RxNorm ingredients
- ndc_bridge_entities.json - NDC → RxCUI mappings  
- pubchem_properties.json - PubChem chemical properties

Output:
- grc20_triples.json - Combined GRC-20 entities ready for loading

Usage:
    python 01_convert_staging.py [--staging-dir DIR] [--output FILE]
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from base_converter import GRC20BaseConverter

BASE_DIR = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DEFAULT_STAGING_DIR = BASE_DIR / "data" / "grc20_v2"
DEFAULT_OUTPUT = BASE_DIR / "data" / "grc20_v2" / "grc20_triples.json"


class StagingToTriplesConverter(GRC20BaseConverter):
    """Converts staging JSONs to GRC-20 triples."""
    
    def __init__(self, staging_dir: Path = None):
        super().__init__()
        self.staging_dir = staging_dir or DEFAULT_STAGING_DIR
        # Extend parent stats with our own
        self.stats.update({
            "rxnorm_entities": 0,
            "ndc_entities": 0,
            "pubchem_enriched": 0,
            "properties_added": 0,
            "properties_skipped": 0,
            "relations_created": 0,
        })
        # Index for looking up entities by RxCUI
        self.rxcui_to_entity = {}
        # Track skipped attributes for reporting
        self.skipped_attributes = defaultdict(int)
        
    def convert_all(self):
        """Run all conversions in order."""
        print("=" * 70)
        print("GRC-20 TRIPLE CONVERTER")
        print("=" * 70)
        
        # Step 1: Load RxNorm entities
        self.load_rxnorm_entities()
        
        # Step 2: Load NDC bridge
        self.load_ndc_bridge()
        
        # Step 3: Enrich with PubChem properties
        self.load_pubchem_properties()
        
        print("\n" + "=" * 70)
        print("CONVERSION SUMMARY")
        print("=" * 70)
        print(f"  RxNorm entities:     {self.stats['rxnorm_entities']:,}")
        print(f"  NDC entities:        {self.stats['ndc_entities']:,}")
        print(f"  PubChem enriched:    {self.stats['pubchem_enriched']:,}")
        print(f"  Properties added:    {self.stats['properties_added']:,}")
        print(f"  Properties skipped:  {self.stats['properties_skipped']:,}")
        print(f"  Relations created:   {self.stats['relations_created']:,}")
        
        # Report skipped attributes
        if self.skipped_attributes:
            print("\n  ⚠️  SKIPPED ATTRIBUTES (not in schema):")
            for attr, count in sorted(self.skipped_attributes.items(), key=lambda x: -x[1]):
                print(f"     - {attr}: {count:,} values skipped")
            print("\n  → Add these to pharma_schema.py to include in future runs")
        
    def _safe_triple(self, entity_id: str, attr_name: str, value):
        """
        Create a triple if attribute exists in schema, otherwise track as skipped.
        
        Returns:
            tuple: (triple_dict or None, was_skipped: bool)
        """
        try:
            triple = self.schema.triple(entity_id, attr_name, value)
            return triple, False
        except KeyError:
            self.skipped_attributes[attr_name] += 1
            self.stats["properties_skipped"] += 1
            return None, True
        
    def load_rxnorm_entities(self):
        """Load RxNorm staging file and create entities."""
        print("\n[1/3] Loading RxNorm entities...")
        
        rxnorm_file = self.staging_dir / "rxnorm_entities.json"
        if not rxnorm_file.exists():
            print(f"  ⚠️ File not found: {rxnorm_file}")
            return
        
        with open(rxnorm_file, 'r') as f:
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
        
        entities = data.get("entities", [])
        print(f"  Found {len(entities):,} entities in staging file")
        
        for entity_data in entities:
            entity_id = entity_data.get("entity")
            name = entity_data.get("name", "")
            rxcui = entity_data.get("rxcui", "")
            tty = entity_data.get("tty", "")
            
            # Store in our index
            if rxcui:
                self.rxcui_to_entity[rxcui] = entity_id
            
            # Build triples from entity data
            triples = []
            
            # Add name
            if name:
                triple, _ = self._safe_triple(entity_id, "name", name)
                if triple:
                    triples.append(triple)
            
            # Add RxCUI
            if rxcui:
                triple, _ = self._safe_triple(entity_id, "rxcui", rxcui)
                if triple:
                    triples.append(triple)
            
            # Add TTY
            if tty:
                triple, _ = self._safe_triple(entity_id, "tty", tty)
                if triple:
                    triples.append(triple)
            
            # Add type based on TTY
            entity_type = self._tty_to_type(tty)
            triple, _ = self._safe_triple(entity_id, "type", entity_type)
            if triple:
                triples.append(triple)
            
            # Add provenance relation
            if prov_id:
                triples.append({
                    "entity": entity_id,
                    "attribute": self.schema.rel("has_provenance"),
                    "value": {"type": 1, "value": prov_id},
                })
            
            # Store the entity
            self.entities.append({
                "entity": entity_id,
                "triples": triples,
            })
            self.stats["rxnorm_entities"] += 1
        
        print(f"  ✅ Converted {self.stats['rxnorm_entities']:,} RxNorm entities")
        
    def load_ndc_bridge(self):
        """Load NDC bridge staging file and create NDC entities + relations."""
        print("\n[2/3] Loading NDC bridge...")
        
        ndc_file = self.staging_dir / "ndc_bridge_entities.json"
        if not ndc_file.exists():
            print(f"  ⚠️ File not found: {ndc_file}")
            return
        
        with open(ndc_file, 'r') as f:
            data = json.load(f)
        
        prov_id = data.get("provenance_entity")
        if not prov_id:
            prov_id = self.create_provenance(
                source="FDA NDC Directory",
                citation="FDA National Drug Code Directory",
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
            )
        
        entities = data.get("entities", [])
        print(f"  Found {len(entities):,} NDC entities in staging file")
        
        for entity_data in entities:
            entity_id = entity_data.get("entity")
            ndc_code = entity_data.get("ndc_code", "")
            rxcui = entity_data.get("rxcui", "")
            
            # Create NDC entity triples
            triples = []
            
            if ndc_code:
                triple, _ = self._safe_triple(entity_id, "ndc_code", ndc_code)
                if triple:
                    triples.append(triple)
                triple, _ = self._safe_triple(entity_id, "name", ndc_code)
                if triple:
                    triples.append(triple)
            
            triple, _ = self._safe_triple(entity_id, "type", "NDC")
            if triple:
                triples.append(triple)
            
            if prov_id:
                triples.append({
                    "entity": entity_id,
                    "attribute": self.schema.rel("has_provenance"),
                    "value": {"type": 1, "value": prov_id},
                })
            
            self.entities.append({
                "entity": entity_id,
                "triples": triples,
            })
            self.stats["ndc_entities"] += 1
            
            # Create MAPS_TO_RXCUI relation if RxCUI exists
            if rxcui and rxcui in self.rxcui_to_entity:
                ingredient_id = self.rxcui_to_entity[rxcui]
                self.relations.append({
                    "entity": entity_id,
                    "triples": [{
                        "entity": entity_id,
                        "attribute": self.schema.rel("maps_to_rxcui"),
                        "value": {"type": 1, "value": ingredient_id},
                    }],
                })
                self.stats["relations_created"] += 1
        
        print(f"  ✅ Converted {self.stats['ndc_entities']:,} NDC entities")
        print(f"  ✅ Created {self.stats['relations_created']:,} MAPS_TO_RXCUI relations")
        
    def load_pubchem_properties(self):
        """Load PubChem properties and enrich existing entities."""
        print("\n[3/3] Loading PubChem properties...")
        
        pubchem_file = self.staging_dir / "pubchem_properties.json"
        if not pubchem_file.exists():
            print(f"  ⚠️ File not found: {pubchem_file}")
            return
        
        with open(pubchem_file, 'r') as f:
            data = json.load(f)
        
        prov_id = data.get("provenance_entity")
        if not prov_id:
            prov_id = self.create_provenance(
                source="PubChem",
                citation="PubChem Compound Database, NCBI",
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
                source_url="https://pubchem.ncbi.nlm.nih.gov/",
            )
        
        enriched_cids = data.get("enriched_cids", {})
        print(f"  Found {len(enriched_cids):,} enriched CIDs")
        
        # Build entity lookup
        entity_lookup = {e["entity"]: e for e in self.entities}
        
        for rxcui, cid_data in enriched_cids.items():
            entity_id = cid_data.get("entity_id")
            if not entity_id or entity_id not in entity_lookup:
                continue
            
            properties = cid_data.get("properties", {})
            entity = entity_lookup[entity_id]
            
            # Add property triples with graceful handling
            for prop_key, value in properties.items():
                if value:
                    # Map staging property names to schema attribute names
                    attr_name = self._map_property_to_attr(prop_key)
                    triple, skipped = self._safe_triple(entity_id, attr_name, str(value))
                    if triple:
                        entity["triples"].append(triple)
                        self.stats["properties_added"] += 1
            
            # Add CID
            cid = cid_data.get("cid")
            if cid:
                triple, _ = self._safe_triple(entity_id, "pubchem_cid", str(cid))
                if triple:
                    entity["triples"].append(triple)
                    self.stats["properties_added"] += 1
            
            # Add provenance
            if prov_id:
                entity["triples"].append({
                    "entity": entity_id,
                    "attribute": self.schema.rel("has_provenance"),
                    "value": {"type": 1, "value": prov_id},
                })
            
            self.stats["pubchem_enriched"] += 1
        
        print(f"  ✅ Enriched {self.stats['pubchem_enriched']:,} entities")
        print(f"  ✅ Added {self.stats['properties_added']:,} property triples")
        
    def _map_property_to_attr(self, prop_key: str) -> str:
        """Map staging property names to schema attribute names."""
        # Direct mappings (staging name -> schema name)
        mapping = {
            "smiles": "smiles",
            "inchikey": "inchikey",
            "iupac_name": "iupac_name",
            "pubchem_cid": "pubchem_cid",
            # These need to be added to schema:
            "pubchem_date": "pubchem_date",
            "pmid": "pmid",
            "sid": "sid",
            "mesh_classes": "mesh_classes",
        }
        return mapping.get(prop_key, prop_key)
        
    def _tty_to_type(self, tty: str) -> str:
        """Convert RxNorm TTY to entity type."""
        tty_map = {
            "IN": "Ingredient",
            "PIN": "Ingredient",
            "MIN": "Ingredient",
            "SCD": "ClinicalDrug",
            "SBD": "BrandedDrug",
            "BN": "BrandName",
            "DF": "DoseForm",
            "DFG": "DoseFormGroup",
        }
        return tty_map.get(tty, "Drug")


def main():
    parser = argparse.ArgumentParser(description="Convert staging JSONs to GRC-20 triples")
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING_DIR,
                        help="Directory containing staging JSONs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Output GRC-20 triples file")
    args = parser.parse_args()
    
    converter = StagingToTriplesConverter(staging_dir=args.staging_dir)
    converter.convert_all()
    
    # Export
    print("\n" + "=" * 70)
    print("EXPORTING")
    print("=" * 70)
    converter.export(args.output.name)
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
