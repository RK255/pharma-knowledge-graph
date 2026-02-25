#!/usr/bin/env python3
"""
Pipeline Step 5.1: Create Name-Based Ingredient Bridge

Creates HAS_INGREDIENT_NAME relationships between FDA entities and RxNorm ingredients
when the NDC bridge is unavailable. Uses exact name matching (case-insensitive).

Provenance:
- Each relationship gets a provenance_hash
- A Provenance node stores batch metadata
- Entry added to provenance_ledger.json

Usage:
    python 01_name_bridge.py [--dry-run]
"""

import json
import hashlib
import argparse
from datetime import datetime
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "Nani*48301")
PROVENANCE_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/provenance_ledger.json"

def create_name_bridge(dry_run=False):
    """Create HAS_INGREDIENT_NAME relationships with full provenance."""
    
    provenance = {
        "source": "FDA DailyMed + RxNorm name matching",
        "method": "exact_lower_case_match",
        "created_at": datetime.now().isoformat(),
        "version": "v1.0.0",
        "description": "Links FDA entities to RxNorm ingredients by exact name match when NDC bridge unavailable",
        "input_sources": ["Neo4j Entity nodes", "Neo4j Ingredient nodes"],
        "exclusion_criteria": [
            "Entities with existing NDC→Ingredient path",
            "Drug names < 4 characters",
            "Entity names = 'unknown drug'"
        ],
        "relationship_type": "HAS_INGREDIENT_NAME",
        "confidence": "exact_match"
    }
    
    provenance_hash = hashlib.sha256(
        json.dumps(provenance, sort_keys=True).encode()
    ).hexdigest()[:16]
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    
    with driver.session(database="neo4j") as session:
        # Ensure index exists
        print("Ensuring indexes...")
        session.run("CREATE INDEX IF NOT EXISTS FOR (e:Entity) ON (e.fda_set_id)")
        session.run("CREATE INDEX IF NOT EXISTS FOR (e:Entity) ON (e.name)")
        
        # Get ingredients lookup
        print("Loading ingredient names...")
        ingredients = session.run("""
            MATCH (i:Ingredient)
            RETURN i.name as name, i.rxcui as rxcui
        """).data()
        
        ing_lookup = {}
        for i in ingredients:
            key = i['name'].lower().strip()
            if key not in ing_lookup:
                ing_lookup[key] = i['rxcui']
        
        print(f"Loaded {len(ing_lookup):,} unique ingredient names")
        
        # Get entities without NDC enrichment
        print("Finding entities without NDC enrichment...")
        entities = session.run("""
            MATCH (e:Entity)
            WHERE e.name IS NOT NULL AND e.name <> ''
            AND NOT (e)-[:HAS_NDC]->()-[:MAPS_TO_RXCUI]->()-[:CONSTITUTES]->()<-[:HAS_INGREDIENT]-(:Ingredient)
            RETURN e.name as name, e.fda_set_id as set_id
        """).data()
        
        print(f"Found {len(entities):,} entities to process")
        
        # Match names
        print("Matching names...")
        matches = []
        for e in entities:
            name = e['name'].lower().strip()
            if len(name) > 3 and name != 'unknown drug' and name in ing_lookup:
                matches.append({
                    'set_id': e['set_id'],
                    'name': e['name'],
                    'rxcui': ing_lookup[name]
                })
        
        print(f"Found {len(matches):,} exact name matches")
        
        if dry_run:
            print("DRY RUN - no changes made")
            driver.close()
            return
        
        if not matches:
            print("No matches to create")
            driver.close()
            return
        
        # Create relationships in batches
        print("Creating relationships...")
        batch_size = 1000
        created = 0
        
        for i in range(0, len(matches), batch_size):
            batch = matches[i:i+batch_size]
            result = session.run("""
                UNWIND $batch as m
                MATCH (e:Entity {fda_set_id: m.set_id})
                MATCH (i:Ingredient {rxcui: m.rxcui})
                MERGE (e)-[r:HAS_INGREDIENT_NAME]->(i)
                SET r.match_type = 'exact',
                    r.source = 'name_fallback',
                    r.provenance_hash = $hash,
                    r.created_at = $created
                RETURN count(r) as cnt
            """, batch=batch, hash=provenance_hash, created=provenance['created_at'])
            
            cnt = result.single()['cnt']
            created += cnt
            if (i // batch_size) % 5 == 0:
                print(f"  Progress: {created:,} / {len(matches):,}")
        
        print(f"\nTotal created: {created:,} relationships")
        
        # Store provenance node
        session.run("""
            MERGE (p:Provenance {hash: $hash})
            SET p += $props
        """, hash=provenance_hash, props={
            **provenance,
            'entity_count': len(matches),
            'relationship_count': created
        })
        
        print(f"Provenance hash: {provenance_hash}")
    
    driver.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Count only, don't create")
    args = parser.parse_args()
    create_name_bridge(dry_run=args.dry_run)
