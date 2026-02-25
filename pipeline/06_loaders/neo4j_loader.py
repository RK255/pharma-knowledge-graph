#!/usr/bin/env python3
"""
Neo4j Unified Parallel Loader - Multithreaded Version
======================================================

Uses ThreadPoolExecutor for parallel batch loading.
Each thread has its own Neo4j session for maximum throughput.

CREATED: 2026-02-22
"""

import json
import os
import time
import threading
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from neo4j import GraphDatabase

# =============================================================================
# CONFIGURATION
# =============================================================================

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "Nani*48301")

BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
DATA_DIR = f"{BASE_DIR}/data/import_csvs"

# Parallelism settings
MAX_WORKERS = 8  # Number of parallel threads
BATCH_SIZE = 2000  # Entities per batch
REL_BATCH_SIZE = 5000  # Relationships per batch

# GRC-20 Attribute mappings
ATTR_MAP = {
    "LuBWqZAu6pz54eiJS5mLv8": "name",
    "Jfmby78N4BCseZinBmdVov8": "type",
    "RxCui12345678901234IJ": "rxcui",
    "NdcCode1234567890AB": "ndc_code",
    "CzNrWVPayq5EB1HXncQFD5": "fda_set_id",
    "Manufacturer12345678EF": "manufacturer",
    "IsRxNorm1234567890GH": "is_rxnorm",
    "TtyCode123456789012AB": "tty",
    "PrimaryTty12345678CD": "primary_tty",
    "Tier1234567890123456EF": "tier",
    "ProvRxNorm12345678IJ": "provenance",
    "HasNdc12345678901234UV": "HAS_NDC",
    "EquivalentTo12345678YZ": "EQUIVALENT_TO",
    "MapsToRxcui12345678WX": "MAPS_TO_RXCUI",
    "HasIngredient123456MN": "HAS_INGREDIENT",
    "HasDoseForm12345678OP": "HAS_DOSE_FORM",
    "HasBrand1234567890QR": "HAS_BRAND",
    "IsA1234567890123456AB": "ISA",
    "InverseIsa12345678CD": "INVERSE_ISA",
}

TYPE_IDS = {
    "GSyVUMkj1HnCEC2ZUdKgD4": "PackageInsert",
    "92foNtgvw8o7s6GRgk8kCQ": "NDC",
    "XJoyWEWqNoLEkrMiiQXwuE": "Drug",
}

TTY_LABELS = {
    'IN': 'Ingredient', 'PIN': 'Ingredient', 'MIN': 'Ingredient',
    'SCD': 'ClinicalDrug', 'SBD': 'BrandedDrug',
    'BN': 'BrandName', 'DF': 'DoseForm',
}


# =============================================================================
# PARALLEL LOADER
# =============================================================================

class ParallelLoader:
    def __init__(self, uri: str, user: str, password: str, workers: int = MAX_WORKERS):
        self.uri = uri
        self.user = user
        self.password = password
        self.workers = workers
        self.driver = GraphDatabase.driver(uri, auth=(user, password),
                                           max_connection_pool_size=workers * 2)
        self.stats = defaultdict(int)
        self.stats_lock = threading.Lock()
        self.entity_to_internal = {}
        self.rxcui_to_entity = {}
        self.ndc_to_rxcui = []
        
    def close(self):
        self.driver.close()
    
    def _get_session(self):
        """Get a new session for parallel work"""
        return self.driver.session()
    
    def run(self, rxnorm_file: str, ndc_file: str, clear: bool = True):
        """Run the complete loading pipeline"""
        print("=" * 80)
        print("NEO4J UNIFIED PARALLEL LOADER")
        print(f"Workers: {self.workers} | Batch size: {BATCH_SIZE}")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        start_total = time.time()
        
        # Step 1: Clear and setup
        if clear:
            self._clear_and_setup()
        
        # Step 2: Parse files
        rxnorm_data = self._parse_grc20_file(rxnorm_file, "RxNorm")
        ndc_data = self._parse_grc20_file(ndc_file, "NDC")
        
        # Step 3: Load entities in parallel
        self._load_entities_parallel(rxnorm_data, ndc_data)
        
        # Step 4: Build ID mapping
        self._build_id_mapping()
        
        # Step 5: Load relationships in parallel
        self._load_relationships_parallel(rxnorm_data, ndc_data)
        
        # Step 6: Create cross-links
        self._create_cross_links_parallel()
        
        # Step 6.5: Classify NDC-RxNorm confidence
        self._classify_ndc_confidence()
        
        # Step 7: Verify
        self._verify()
        
        elapsed = time.time() - start_total
        print("\n" + "=" * 80)
        print(f"COMPLETE in {elapsed:.1f}s ({elapsed/60:.1f} min)")
        print(f"Entities: {self.stats['entities']:,} | Relationships: {self.stats['relationships']:,}")
        print("=" * 80)
    
    # -------------------------------------------------------------------------
    # STEP 1: Clear and Setup
    # -------------------------------------------------------------------------
    
    def _clear_and_setup(self):
        print("\n[1/7] Clearing database and creating indexes...")
        with self._get_session() as session:
            result = session.run("MATCH (n) RETURN count(n) as c").single()
            if result and result["c"] > 0:
                session.run("MATCH (n) DETACH DELETE n")
                print(f"  Cleared {result['c']:,} nodes")
            
            indexes = [
                "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE",
                "CREATE INDEX name_idx IF NOT EXISTS FOR (n:Entity) ON (n.name)",
                "CREATE INDEX rxcui_idx IF NOT EXISTS FOR (n:RxNormConcept) ON (n.rxcui)",
                "CREATE INDEX ndc_idx IF NOT EXISTS FOR (n:NDC) ON (n.ndc_code)",
                "CREATE INDEX tty_idx IF NOT EXISTS FOR (n:RxNormConcept) ON (n.primary_tty)",
            ]
            for idx in indexes:
                try:
                    session.run(idx)
                except:
                    pass
        print("  ✅ Done")
    
    # -------------------------------------------------------------------------
    # STEP 2: Parse GRC-20 Files
    # -------------------------------------------------------------------------
    
    def _parse_grc20_file(self, filepath: str, source: str) -> dict:
        print(f"\n[2/7] Parsing {source}...")
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        entities = []
        relationships = []
        
        for entity in data.get("entities", []):
            entity_id = entity["entity"]
            props = {"entity_id": entity_id}
            label = "RxNormConcept" if source == "RxNorm" else "Entity"
            rxcui = None
            
            for triple in entity.get("triples", []):
                attr_id = triple.get("attribute", "")
                value = triple.get("value", {}).get("value", "")
                attr_name = ATTR_MAP.get(attr_id, attr_id)
                
                if attr_name == "name":
                    props["name"] = value
                elif attr_name == "rxcui":
                    props["rxcui"] = value
                    rxcui = value
                elif attr_name == "ndc_code":
                    props["ndc_code"] = value
                elif attr_name == "fda_set_id":
                    props["fda_set_id"] = value
                elif attr_name == "manufacturer":
                    props["manufacturer"] = value
                elif attr_name == "tty":
                    props["tty"] = value
                elif attr_name == "primary_tty":
                    props["primary_tty"] = value
                    label = TTY_LABELS.get(value, label)
                elif attr_name == "tier":
                    props["tier"] = value
                elif attr_name == "provenance":
                    props["provenance"] = value
                elif attr_name == "is_rxnorm":
                    props["is_rxnorm"] = str(value).lower() == "true"
                elif attr_name == "type":
                    label = TYPE_IDS.get(value, label)
                elif attr_name in ["HAS_NDC", "EQUIVALENT_TO", "HAS_INGREDIENT", 
                                   "HAS_DOSE_FORM", "HAS_BRAND", "ISA", "INVERSE_ISA"]:
                    relationships.append({"from": entity_id, "to": value, "type": attr_name})
            
            entities.append({"id": entity_id, "label": label, "props": props})
            
            if source == "RxNorm" and rxcui:
                self.rxcui_to_entity[rxcui] = entity_id
            elif source == "NDC" and rxcui:
                self.ndc_to_rxcui.append((entity_id, rxcui))
        
        print(f"  ✅ {len(entities):,} entities, {len(relationships):,} relationships")
        return {"entities": entities, "relationships": relationships}
    
    # -------------------------------------------------------------------------
    # STEP 3: Load Entities in Parallel
    # -------------------------------------------------------------------------
    
    def _load_entities_parallel(self, rxnorm_data: dict, ndc_data: dict):
        print(f"\n[3/7] Loading entities in parallel ({self.workers} workers)...")
        
        all_entities = rxnorm_data["entities"] + ndc_data["entities"]
        
        # Group by label
        by_label = defaultdict(list)
        for e in all_entities:
            by_label[e["label"]].append(e)
        
        print(f"  Total: {len(all_entities):,} entities across {len(by_label)} labels")
        for label, items in by_label.items():
            print(f"    • {label}: {len(items):,}")
        
        start = time.time()
        loaded = 0
        
        # Create batches for parallel processing
        batches = []
        for label, items in by_label.items():
            for i in range(0, len(items), BATCH_SIZE):
                batch = items[i:i + BATCH_SIZE]
                batches.append((label, batch))
        
        print(f"  Processing {len(batches)} batches...")
        
        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._load_entity_batch, label, batch): len(batch)
                for label, batch in batches
            }
            
            for future in as_completed(futures):
                count = futures[future]
                try:
                    future.result()
                    with self.stats_lock:
                        loaded += count
                        self.stats["entities"] += count
                    if loaded % 50000 == 0:
                        elapsed = time.time() - start
                        rate = loaded / elapsed if elapsed > 0 else 0
                        print(f"    {loaded:,}/{len(all_entities):,} ({rate:.0f}/sec)")
                except Exception as e:
                    print(f"    Error: {e}")
        
        elapsed = time.time() - start
        print(f"  ✅ Loaded {loaded:,} entities in {elapsed:.1f}s ({loaded/elapsed:.0f}/sec)")
    
    def _load_entity_batch(self, label: str, batch: list):
        """Load a single batch of entities (runs in thread)"""
        with self._get_session() as session:
            batch_data = []
            for e in batch:
                props = {}
                for k, v in e["props"].items():
                    props[k] = json.dumps(v) if isinstance(v, list) else v
                batch_data.append(props)
            
            query = f"""
            UNWIND $batch AS props
            MERGE (n:{label} {{entity_id: props.entity_id}})
            SET n += props
            """
            session.run(query, batch=batch_data).consume()
    
    # -------------------------------------------------------------------------
    # STEP 4: Build ID Mapping
    # -------------------------------------------------------------------------
    
    def _build_id_mapping(self):
        print("\n[4/7] Building ID mapping...")
        start = time.time()
        
        with self._get_session() as session:
            result = session.run("MATCH (n) WHERE n.entity_id IS NOT NULL RETURN n.entity_id AS eid, id(n) AS nid")
            for record in result:
                self.entity_to_internal[record['eid']] = record['nid']
        
        elapsed = time.time() - start
        print(f"  ✅ Mapped {len(self.entity_to_internal):,} entities in {elapsed:.1f}s")
    
    # -------------------------------------------------------------------------
    # STEP 5: Load Relationships in Parallel
    # -------------------------------------------------------------------------
    
    def _load_relationships_parallel(self, rxnorm_data: dict, ndc_data: dict):
        print(f"\n[5/7] Loading relationships in parallel ({self.workers} workers)...")
        
        all_rels = rxnorm_data["relationships"] + ndc_data["relationships"]
        
        # Filter valid
        valid_rels = []
        for rel in all_rels:
            from_id = self.entity_to_internal.get(rel["from"])
            to_id = self.entity_to_internal.get(rel["to"])
            if from_id is not None and to_id is not None:
                valid_rels.append({"from_id": from_id, "to_id": to_id, "type": rel["type"]})
        
        print(f"  Valid: {len(valid_rels):,}/{len(all_rels):,}")
        
        # Group by type
        by_type = defaultdict(list)
        for rel in valid_rels:
            by_type[rel["type"]].append(rel)
        
        for rel_type, rels in sorted(by_type.items(), key=lambda x: -len(x[1])):
            print(f"    • {rel_type}: {len(rels):,}")
        
        start = time.time()
        loaded = 0
        
        # Create batches
        batches = []
        for rel_type, rels in by_type.items():
            for i in range(0, len(rels), REL_BATCH_SIZE):
                batch = rels[i:i + REL_BATCH_SIZE]
                batches.append((rel_type, batch))
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._load_rel_batch, rel_type, batch): len(batch)
                for rel_type, batch in batches
            }
            
            for future in as_completed(futures):
                count = futures[future]
                try:
                    future.result()
                    with self.stats_lock:
                        loaded += count
                        self.stats["relationships"] += count
                    if loaded % 100000 == 0:
                        elapsed = time.time() - start
                        rate = loaded / elapsed if elapsed > 0 else 0
                        print(f"    {loaded:,}/{len(valid_rels):,} ({rate:.0f}/sec)")
                except Exception as e:
                    print(f"    Error: {e}")
        
        elapsed = time.time() - start
        print(f"  ✅ Created {loaded:,} relationships in {elapsed:.1f}s ({loaded/elapsed:.0f}/sec)")
    
    def _load_rel_batch(self, rel_type: str, batch: list):
        """Load a single batch of relationships (runs in thread)"""
        safe_type = rel_type.upper().replace("-", "_")
        
        with self._get_session() as session:
            query = f"""
            UNWIND $batch AS rel
            MATCH (from) WHERE id(from) = rel.from_id
            MATCH (to) WHERE id(to) = rel.to_id
            MERGE (from)-[r:{safe_type}]->(to)
            """
            session.run(query, batch=batch).consume()
    
    # -------------------------------------------------------------------------
    # STEP 6: Create Cross-Links in Parallel
    # -------------------------------------------------------------------------
    
    def _create_cross_links_parallel(self):
        print(f"\n[6/7] Creating cross-links ({self.workers} workers)...")
        
        cross_links = []
        for ndc_eid, rxcui in self.ndc_to_rxcui:
            rxnorm_eid = self.rxcui_to_entity.get(rxcui)
            if rxnorm_eid:
                ndc_internal = self.entity_to_internal.get(ndc_eid)
                rxnorm_internal = self.entity_to_internal.get(rxnorm_eid)
                if ndc_internal is not None and rxnorm_internal is not None:
                    cross_links.append({"from_id": ndc_internal, "to_id": rxnorm_internal})
        
        print(f"  Valid cross-links: {len(cross_links):,}")
        
        if not cross_links:
            print("  No cross-links to create")
            return
        
        start = time.time()
        created = 0
        
        # Create batches
        batches = []
        for i in range(0, len(cross_links), REL_BATCH_SIZE):
            batches.append(cross_links[i:i + REL_BATCH_SIZE])
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._load_crosslink_batch, batch): len(batch) for batch in batches}
            
            for future in as_completed(futures):
                count = futures[future]
                try:
                    future.result()
                    created += count
                    self.stats["cross_links"] += count
                except Exception as e:
                    print(f"    Error: {e}")
        
        elapsed = time.time() - start
        print(f"  ✅ Created {created:,} cross-links in {elapsed:.1f}s ({created/elapsed:.0f}/sec)")
    
    def _load_crosslink_batch(self, batch: list):
        """Load cross-link batch"""
        with self._get_session() as session:
            query = """
            UNWIND $batch AS rel
            MATCH (from) WHERE id(from) = rel.from_id
            MATCH (to) WHERE id(to) = rel.to_id
            MERGE (from)-[:MAPS_TO_RXCUI]->(to)
            """
            session.run(query, batch=batch).consume()
    
    # -------------------------------------------------------------------------
    # STEP 7: Verify
    # -------------------------------------------------------------------------
    

    def _classify_ndc_confidence(self):
        """
        Classify MAPS_TO_RXCUI relationships by confidence level.
        
        HIGH: FDA drug name contains at least one RxNorm ingredient
        LOW: FDA name contains NONE of the RxNorm ingredients (conflict)
        """
        print(f"\n[6.5/7] Classifying NDC-RxNorm confidence...")
        
        with self._get_session() as session:
            result = session.run("""
                MATCH ()-[r:MAPS_TO_RXCUI]->()
                WHERE r.confidence IS NULL
                RETURN count(r) as total
            """)
            total = result.single()["total"]
            
            if total == 0:
                print("  All relationships already classified")
                return
            
            print(f"  Classifying {total:,} relationships...")
            
            start = time.time()
            classified = 0
            
            while True:
                result = session.run("""
                    MATCH (fda:Entity)-[:HAS_NDC]->(ndc:Entity)-[r:MAPS_TO_RXCUI]->(cd:ClinicalDrug)
                    WHERE fda.fda_set_id IS NOT NULL AND ndc.is_rxnorm = true AND r.confidence IS NULL
                    OPTIONAL MATCH (cd)-[:CONSTITUTES]->(scc)<-[:HAS_INGREDIENT]-(ing:Ingredient)
                    WITH fda, ndc, cd, r, 
                         toLower(fda.name) as fda_lower,
                         collect(DISTINCT toLower(ing.name)) as ingredients
                    WITH fda, ndc, cd, r, fda_lower, ingredients,
                         ANY(ing_name IN ingredients WHERE fda_lower CONTAINS ing_name) as has_match
                    LIMIT 5000
                    SET r.confidence = CASE WHEN has_match THEN 'HIGH' ELSE 'LOW' END,
                        r.conflict_reason = CASE 
                            WHEN has_match THEN 'FDA-RxNorm agreement verified'
                            ELSE 'FDA-RxNorm mismatch: drug name does not match any RxNorm ingredients'
                        END,
                        r.authoritative_source = CASE 
                            WHEN has_match THEN 'FDA+RxNorm'
                            ELSE 'RxNorm'
                        END,
                        r.classified_at = datetime()
                    RETURN count(r) as batch_count
                """)
                
                batch_count = result.single()["batch_count"]
                if batch_count == 0:
                    break
                    
                classified += batch_count
                if classified % 20000 == 0:
                    print(f"    {classified:,}/{total:,}")
            
            elapsed = time.time() - start
            print(f"  ✅ Classified {classified:,} relationships in {elapsed:.1f}s")
            
            result = session.run("""
                MATCH ()-[r:MAPS_TO_RXCUI]->()
                RETURN count(r) as total,
                       count(CASE WHEN r.confidence = 'HIGH' THEN 1 END) as high,
                       count(CASE WHEN r.confidence = 'LOW' THEN 1 END) as low
            """)
            stats = result.single()
            print(f"     HIGH confidence: {stats['high']:,} ({100*stats['high']/stats['total']:.1f}%)")
            print(f"     LOW confidence:  {stats['low']:,} ({100*stats['low']/stats['total']:.1f}%)")
            
            self.stats["high_confidence"] = stats['high']
            self.stats["low_confidence"] = stats['low']

    def _verify(self):
        print("\n[7/7] Verification...")
        
        with self._get_session() as session:
            print("\n  Nodes by label:")
            result = session.run("MATCH (n) RETURN labels(n)[0] as l, count(n) as c ORDER BY c DESC")
            for r in result:
                print(f"    • {r['l']}: {r['c']:,}")
            
            print("\n  Relationships by type:")
            result = session.run("MATCH ()-[r]->() RETURN type(r) as t, count(r) as c ORDER BY c DESC LIMIT 10")
            for r in result:
                print(f"    • {r['t']}: {r['c']:,}")
            
            print("\n  Sample: Tamsulosin")
            result = session.run("""
                MATCH (r:RxNormConcept) WHERE r.name CONTAINS 'Tamsulosin'
                OPTIONAL MATCH (r)-[rel]-(other)
                RETURN r.name as name, r.rxcui as rxcui, count(DISTINCT rel) as conns LIMIT 1
            """)
            for r in result:
                print(f"    {r['name']} (RxCUI: {r['rxcui']}, Connections: {r['conns']})")


# =============================================================================
# MAIN
# =============================================================================

def main():
    loader = ParallelLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, workers=MAX_WORKERS)
    
    try:
        loader.run(
            f"{DATA_DIR}/grc20_rxnorm_data.json",
            f"{DATA_DIR}/grc20_ndc_tether_data.json",
            clear=True
        )
    finally:
        loader.close()


if __name__ == "__main__":
    main()
