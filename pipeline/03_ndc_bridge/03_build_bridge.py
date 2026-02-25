#!/usr/bin/env python3
"""
NDC Bridge Builder v1
=====================
Creates GRC-20 compliant NDC bridge entities linking:
- DailyMed drug labels (Redis) 
- RxNorm concepts (Neo4j)

This enables cross-graph queries via the common NDC denominator.
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional

# Add parent paths for imports
sys.path.insert(0, '/mnt/fast_raid/server_projects/Geo/graph_workshop/scripts/production/rxnorm')

import redis
from neo4j import GraphDatabase

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
OUTPUT_DIR = f"{BASE_DIR}/scripts/development/output"
BRIDGE_DIR = f"{BASE_DIR}/scripts/development/ndc_bridge"

# Redis Configuration
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# Neo4j Configuration  
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Nani*48301"

# Files
NDC_TTY_FILE = f"{BASE_DIR}/data/raw_data/ndc_tty_distribution.json"
RXNORM_NDC_FILE = f"{BASE_DIR}/data/raw_data/rxnorm_ndcs.txt"

# =============================================================================
# NDC NORMALIZATION
# =============================================================================

def normalize_ndc(ndc: str) -> str:
    """
    Normalize NDC to 5-4-2 hyphenated format.
    Handles: 5-4-2, 5-3-2, 4-4-2, 5-4-1, 5-4-2, plain 11-digit, plain 10-digit
    """
    if not ndc:
        return ""
    
    # Remove any existing hyphens and spaces
    ndc_clean = ndc.strip().replace("-", "").replace(" ", "")
    
    # Handle different lengths
    if len(ndc_clean) == 11:
        # Standard 5-4-2 format (already 11 digits)
        return f"{ndc_clean[:5]}-{ndc_clean[5:9]}-{ndc_clean[9:]}"
    elif len(ndc_clean) == 10:
        # 5-3-2 or 4-4-2 format - assume 5-3-2
        return f"{ndc_clean[:5]}-{ndc_clean[5:8]}-{ndc_clean[8:]}"
    elif len(ndc_clean) == 9:
        # 5-3-1 format
        return f"{ndc_clean[:5]}-{ndc_clean[5:8]}-{ndc_clean[8:]}"
    
    # Return as-is if we can't normalize
    return ndc.strip()


def generate_grc20_id(data: str) -> str:
    """Generate GRC-20 compliant Base58 entity ID"""
    import base58
    hash_bytes = hashlib.sha256(data.encode()).digest()[:16]
    return base58.b58encode(hash_bytes).decode()[:22]


# =============================================================================
# PROVENANCE TRACKING
# =============================================================================

class ProvenanceTracker:
    """Track provenance for GRC-20 compliance"""
    
    def __init__(self):
        self.provenance_records = {}
        self.provenance_hashes = set()
    
    def create_provenance(self, 
                          source: str,
                          source_type: str,
                          source_id: str,
                          target_type: str,
                          target_id: str,
                          linkage_type: str,
                          **kwargs) -> str:
        """Create provenance record and return hash"""
        
        record = {
            "provenance_type": "ndc_bridge",
            "source": source,
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "linkage_type": linkage_type,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs
        }
        
        # Create hash
        record_json = json.dumps(record, sort_keys=True)
        prov_hash = hashlib.sha256(record_json.encode()).hexdigest()[:16]
        record["provenance_hash"] = prov_hash
        
        self.provenance_records[prov_hash] = record
        self.provenance_hashes.add(prov_hash)
        
        return prov_hash
    
    def save(self, output_path: str):
        """Save provenance ledger"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump({
                "provenance_records": self.provenance_records,
                "total_records": len(self.provenance_records),
                "created": datetime.utcnow().isoformat()
            }, f, indent=2)


# =============================================================================
# NDC BRIDGE BUILDER
# =============================================================================

class NDCBridgeBuilder:
    """
    Builds GRC-20 compliant NDC bridge entities.
    
    Architecture:
    - NDC entities stored in Redis (linked to DailyMed drugs)
    - NDC-to-RxCUI mappings stored (linked to Neo4j concepts)
    - Provenance tracked for all linkages
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.provenance = ProvenanceTracker()
        
        # Data structures
        self.daily_med_ndcs: Dict[str, List[dict]] = defaultdict(list)  # normalized_ndc -> [{drug_id, drug_name, original_ndc}]
        self.rxnorm_ndcs: Dict[str, List[str]] = defaultdict(list)  # normalized_ndc -> [rxcuis]
        self.ndc_entities: Dict[str, dict] = {}  # ndc_entity_id -> entity_data
        self.bridge_links: List[dict] = []
        
        # Stats
        self.stats = {
            "daily_med_drugs": 0,
            "daily_med_ndcs": 0,
            "unique_daily_med_ndcs": 0,
            "rxnorm_ndcs": 0,
            "unique_rxnorm_ndcs": 0,
            "matched_ndcs": 0,
            "bridge_entities_created": 0,
            "rxnorm_links": 0,
            "dailymed_links": 0
        }
    
    def close(self):
        self.redis_client.close()
        self.neo4j_driver.close()
    
    def run(self):
        """Main execution"""
        print("=" * 70)
        print("NDC BRIDGE BUILDER v1")
        print("Building GRC-20 compliant NDC bridge entities")
        print("=" * 70)
        
        # Step 1: Load DailyMed NDCs from Redis
        print("\n[1/5] Loading DailyMed NDCs from Redis...")
        self.load_dailymed_ndcs()
        
        # Step 2: Load RxNorm NDCs
        print("\n[2/5] Loading RxNorm NDCs from file...")
        self.load_rxnorm_ndcs()
        
        # Step 3: Create NDC bridge entities
        print("\n[3/5] Creating NDC bridge entities...")
        self.create_bridge_entities()
        
        # Step 4: Store in Redis
        print("\n[4/5] Storing NDC bridge in Redis...")
        self.store_bridge_in_redis()
        
        # Step 5: Update Neo4j with links
        print("\n[5/5] Updating Neo4j with NDC links...")
        self.update_neo4j_links()
        
        # Save outputs
        self.save_outputs()
        
        # Print summary
        self.print_summary()
    
    def load_dailymed_ndcs(self):
        """Load NDCs from DailyMed drugs in Redis"""
        drug_count = 0
        ndc_count = 0
        
        for drug_id, drug_json in self.redis_client.hscan_iter("pharma:enhanced_drugs"):
            try:
                drug_data = json.loads(drug_json)
                drug_name = drug_data.get('name', 'Unknown')
                ndc_str = drug_data.get('ndc', '')
                set_id = drug_data.get('set_id', '')
                
                if not ndc_str:
                    continue
                
                drug_count += 1
                
                # Parse NDCs (comma-separated)
                ndcs = [n.strip() for n in ndc_str.split(',') if n.strip()]
                
                for original_ndc in ndcs:
                    normalized = normalize_ndc(original_ndc)
                    if normalized:
                        self.daily_med_ndcs[normalized].append({
                            "drug_id": drug_id,
                            "drug_name": drug_name,
                            "original_ndc": original_ndc,
                            "set_id": set_id
                        })
                        ndc_count += 1
                        
            except Exception as e:
                print(f"  Error processing drug {drug_id}: {e}")
                continue
        
        self.stats["daily_med_drugs"] = drug_count
        self.stats["daily_med_ndcs"] = ndc_count
        self.stats["unique_daily_med_ndcs"] = len(self.daily_med_ndcs)
        
        print(f"  ✅ Loaded {ndc_count} NDCs from {drug_count} DailyMed drugs")
        print(f"  ✅ {len(self.daily_med_ndcs)} unique NDCs after normalization")
    
    def load_rxnorm_ndcs(self):
        """Load NDCs from RxNorm"""
        # Load from the NDC TTY distribution file
        if os.path.exists(NDC_TTY_FILE):
            print(f"  Loading from {NDC_TTY_FILE}")
            with open(NDC_TTY_FILE, 'r') as f:
                ndc_data = json.load(f)
            
            for ndc, ttys in ndc_data.get('ndc_tty_mapping', {}).items():
                normalized = normalize_ndc(ndc)
                if normalized:
                    # We'll need to look up RxCUIs later from Neo4j
                    self.rxnorm_ndcs[normalized] = ttys
            
            self.stats["rxnorm_ndcs"] = len(ndc_data.get('ndc_tty_mapping', {}))
            self.stats["unique_rxnorm_ndcs"] = len(self.rxnorm_ndcs)
            print(f"  ✅ Loaded {len(ndc_data.get('ndc_tty_mapping', {}))} NDCs from RxNorm")
        
        # Also load from plain text file for completeness
        elif os.path.exists(RXNORM_NDC_FILE):
            print(f"  Loading from {RXNORM_NDC_FILE}")
            with open(RXNORM_NDC_FILE, 'r') as f:
                for line in f:
                    ndc = line.strip()
                    normalized = normalize_ndc(ndc)
                    if normalized:
                        self.rxnorm_ndcs[normalized] = []
            
            self.stats["rxnorm_ndcs"] = self.stats["unique_rxnorm_ndcs"] = len(self.rxnorm_ndcs)
            print(f"  ✅ Loaded {len(self.rxnorm_ndcs)} NDCs from RxNorm")
    
    def create_bridge_entities(self):
        """Create GRC-20 compliant NDC bridge entities"""
        
        # Find matching NDCs (exist in both systems)
        matched_ndcs = set(self.daily_med_ndcs.keys()) & set(self.rxnorm_ndcs.keys())
        self.stats["matched_ndcs"] = len(matched_ndcs)
        
        print(f"  Found {len(matched_ndcs)} NDCs that exist in both DailyMed and RxNorm")
        
        # Create entities for all DailyMed NDCs (whether matched or not)
        for normalized_ndc, drug_list in self.daily_med_ndcs.items():
            # Generate entity ID
            entity_id = generate_grc20_id(f"ndc:{normalized_ndc}")
            
            # Check if this NDC also exists in RxNorm
            has_rxnorm = normalized_ndc in self.rxnorm_ndcs
            rxnorm_ttys = self.rxnorm_ndcs.get(normalized_ndc, [])
            
            # Create GRC-20 entity
            entity = {
                "id": entity_id,
                "normalized_ndc": normalized_ndc,
                "entity_type": "NDC_Bridge",
                "has_dailymed": True,
                "has_rxnorm": has_rxnorm,
                "rxnorm_ttys": rxnorm_ttys,
                "dailymed_drugs": [d['drug_id'] for d in drug_list],
                "dailymed_drug_names": list(set(d['drug_name'] for d in drug_list)),
                "original_ndcs": list(set(d['original_ndc'] for d in drug_list)),
                "triple_count": 0,
                "created": datetime.utcnow().isoformat()
            }
            
            # Create GRC-20 triples
            triples = []
            
            # Triple 1: NDC value
            triples.append({
                "attribute": generate_grc20_id("attr:ndc"),
                "value": normalized_ndc,
                "attribute_type": "ndc_code"
            })
            
            # Triple 2: Entity type
            triples.append({
                "attribute": generate_grc20_id("attr:type"),
                "value": "NDC_Bridge_Entity",
                "attribute_type": "entity_type"
            })
            
            # Triple 3: DailyMed link status
            triples.append({
                "attribute": generate_grc20_id("attr:has_dailymed"),
                "value": "true",
                "attribute_type": "boolean"
            })
            
            # Triple 4: RxNorm link status
            triples.append({
                "attribute": generate_grc20_id("attr:has_rxnorm"),
                "value": str(has_rxnorm).lower(),
                "attribute_type": "boolean"
            })
            
            # Triple 5: Drug count
            triples.append({
                "attribute": generate_grc20_id("attr:drug_count"),
                "value": str(len(drug_list)),
                "attribute_type": "integer"
            })
            
            # Triple 6+: Drug references
            for i, drug in enumerate(drug_list[:5]):  # Limit to 5 for performance
                triples.append({
                    "attribute": generate_grc20_id(f"attr:drug_ref_{i}"),
                    "value": drug['drug_id'],
                    "attribute_type": "entity_reference"
                })
            
            entity["triples"] = triples
            entity["triple_count"] = len(triples)
            
            # Create provenance
            prov_hash = self.provenance.create_provenance(
                source="dailymed_rxnorm_bridge",
                source_type="algorithmic_match",
                source_id=normalized_ndc,
                target_type="NDC_Bridge_Entity",
                target_id=entity_id,
                linkage_type="ndc_normalization",
                dailymed_drugs=len(drug_list),
                rxnorm_match=has_rxnorm
            )
            entity["provenance_hash"] = prov_hash
            
            self.ndc_entities[entity_id] = entity
            
            # Create bridge links for matched NDCs
            if has_rxnorm:
                self.bridge_links.append({
                    "ndc_entity_id": entity_id,
                    "normalized_ndc": normalized_ndc,
                    "dailymed_drugs": [d['drug_id'] for d in drug_list],
                    "rxnorm_ttys": rxnorm_ttys,
                    "provenance_hash": prov_hash
                })
        
        self.stats["bridge_entities_created"] = len(self.ndc_entities)
        print(f"  ✅ Created {len(self.ndc_entities)} NDC bridge entities")
        print(f"  ✅ {len(self.bridge_links)} entities have RxNorm matches")
    
    def store_bridge_in_redis(self):
        """Store NDC bridge entities in Redis"""
        
        # Store in new hash
        pipe = self.redis_client.pipeline()
        
        for entity_id, entity in self.ndc_entities.items():
            # Store entity
            pipe.hset("pharma:ndc_bridge", entity_id, json.dumps(entity))
            
            # Create index by NDC
            pipe.hset("pharma:ndc_index", entity['normalized_ndc'], entity_id)
        
        pipe.execute()
        
        # Verify
        stored_count = self.redis_client.hlen("pharma:ndc_bridge")
        print(f"  ✅ Stored {stored_count} NDC bridge entities in Redis")
        
        self.stats["dailymed_links"] = stored_count
    
    def update_neo4j_links(self):
        """Update Neo4j with NDC links"""
        
        print("  Querying Neo4j for RxCUI-to-NDC mappings...")
        
        # First, we need to get RxCUIs for each NDC from Neo4j
        # Query RXNSAT for NDC relationships
        # Note: This requires NDC data to be in Neo4j
        
        # For now, we'll create a mapping file for later use
        rxnorm_links_created = 0
        
        # Store the mapping for Neo4j import
        neo4j_import_file = f"{OUTPUT_DIR}/ndc_neo4j_import.json"
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        with open(neo4j_import_file, 'w') as f:
            json.dump({
                "bridge_links": self.bridge_links,
                "created": datetime.utcnow().isoformat(),
                "total": len(self.bridge_links)
            }, f, indent=2)
        
        self.stats["rxnorm_links"] = len(self.bridge_links)
        print(f"  ✅ Created Neo4j import file with {len(self.bridge_links)} NDC links")
        print(f"  📁 Saved to: {neo4j_import_file}")
    
    def save_outputs(self):
        """Save all outputs"""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Save provenance
        prov_file = f"{OUTPUT_DIR}/ndc_bridge_provenance.json"
        self.provenance.save(prov_file)
        print(f"\n📁 Saved provenance to: {prov_file}")
        
        # Save bridge entities
        entities_file = f"{OUTPUT_DIR}/ndc_bridge_entities.json"
        with open(entities_file, 'w') as f:
            json.dump({
                "entities": self.ndc_entities,
                "total": len(self.ndc_entities),
                "created": datetime.utcnow().isoformat()
            }, f)
        print(f"📁 Saved entities to: {entities_file}")
        
        # Save statistics
        stats_file = f"{OUTPUT_DIR}/ndc_bridge_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
        print(f"📁 Saved stats to: {stats_file}")
        
        # Save bridge index
        bridge_index = {
            "total_ndc_entities": len(self.ndc_entities),
            "matched_ndcs": self.stats["matched_ndcs"],
            "unique_dailymed_ndcs": self.stats["unique_daily_med_ndcs"],
            "unique_rxnorm_ndcs": self.stats["unique_rxnorm_ndcs"],
            "created": datetime.utcnow().isoformat()
        }
        bridge_index_file = f"{BRIDGE_DIR}/bridge_index.json"
        os.makedirs(BRIDGE_DIR, exist_ok=True)
        with open(bridge_index_file, 'w') as f:
            json.dump(bridge_index, f, indent=2)
        print(f"📁 Saved bridge index to: {bridge_index_file}")
    
    def print_summary(self):
        """Print execution summary"""
        print("\n" + "=" * 70)
        print("NDC BRIDGE BUILD SUMMARY")
        print("=" * 70)
        
        print(f"\nDailyMed (Redis):")
        print(f"  Drugs processed:        {self.stats['daily_med_drugs']:,}")
        print(f"  NDCs extracted:         {self.stats['daily_med_ndcs']:,}")
        print(f"  Unique NDCs:            {self.stats['unique_daily_med_ndcs']:,}")
        
        print(f"\nRxNorm:")
        print(f"  NDCs loaded:            {self.stats['rxnorm_ndcs']:,}")
        print(f"  Unique NDCs:            {self.stats['unique_rxnorm_ndcs']:,}")
        
        print(f"\nBridge Entities:")
        print(f"  NDCs in both systems:   {self.stats['matched_ndcs']:,}")
        print(f"  Bridge entities created: {self.stats['bridge_entities_created']:,}")
        print(f"  DailyMed links:         {self.stats['dailymed_links']:,}")
        print(f"  RxNorm potential links: {self.stats['rxnorm_links']:,}")
        
        match_rate = (self.stats['matched_ndcs'] / max(self.stats['unique_daily_med_ndcs'], 1)) * 100
        print(f"\nMatch Rate: {match_rate:.1f}%")
        
        print(f"\nGRC-20 Compliance:")
        print(f"  Provenance records:     {len(self.provenance.provenance_records):,}")
        print(f"  Entity IDs generated:   {len(self.ndc_entities):,}")
        
        print("\n" + "=" * 70)


if __name__ == "__main__":
    builder = NDCBridgeBuilder()
    try:
        builder.run()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        builder.close()
