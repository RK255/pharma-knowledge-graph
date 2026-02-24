#!/usr/bin/env python3
"""
Data Quality Conflict Detection
Runs at load time to pre-compute FDA-RxNorm conflicts
Stores results in Neo4j for fast querying
"""

import os
from neo4j import GraphDatabase
from datetime import datetime

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Nani*48301")

def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def create_conflict_schema():
    """Create constraints and indexes for conflict tracking"""
    driver = get_driver()
    with driver.session() as session:
        # Create constraint for unique conflicts
        session.run("""
            CREATE CONSTRAINT conflict_id IF NOT EXISTS
            FOR (c:DataQualityConflict) REQUIRE c.conflict_id IS UNIQUE
        """)
        
        # Create indexes for common queries
        session.run("CREATE INDEX conflict_ndc IF NOT EXISTS FOR (c:DataQualityConflict) ON (c.ndc_code)")
        session.run("CREATE INDEX conflict_labeler IF NOT EXISTS FOR (c:DataQualityConflict) ON (c.labeler)")
        session.run("CREATE INDEX conflict_status IF NOT EXISTS FOR (c:DataQualityConflict) ON (c.status)")
        session.run("CREATE INDEX conflict_type IF NOT EXISTS FOR (c:DataQualityConflict) ON (c.conflict_type)")
        
    driver.close()
    print("Created conflict schema")

def detect_and_store_conflicts():
    """Detect all FDA-RxNorm conflicts and store in Neo4j"""
    driver = get_driver()
    detected_at = datetime.utcnow().isoformat()
    
    with driver.session() as session:
        # Clear old conflicts (or mark as superseded)
        result = session.run("""
            MATCH (c:DataQualityConflict)
            SET c.superseded_at = $detected_at
            RETURN count(c) as cleared
        """, detected_at=detected_at)
        cleared = result.single()["cleared"]
        print(f"Marked {cleared} old conflicts as superseded")
        
        # Detect and insert new conflicts
        result = session.run("""
            MATCH (fda:Entity)-[:HAS_NDC]->(ndc:Entity)-[:MAPS_TO_RXCUI]->(cd:ClinicalDrug)-[:CONSTITUTES]->(scc)<-[:HAS_INGREDIENT]-(ing:Ingredient)
            WHERE fda.fda_set_id IS NOT NULL AND ndc.is_rxnorm = true
            OPTIONAL MATCH (cd)-[:CONSTITUTES]->(all_scc)<-[:HAS_INGREDIENT]-(all_ing:Ingredient)
            WITH fda, ndc, cd, ing, 
                 toLower(fda.name) as fda_lower,
                 collect(DISTINCT toLower(all_ing.name)) as all_ingredients
            WITH fda, ndc, cd, ing, fda_lower, all_ingredients,
                 ANY(ing_name IN all_ingredients WHERE fda_lower CONTAINS ing_name) as has_any_match
            WHERE NOT has_any_match
            WITH DISTINCT fda.name as fda_drug_name, 
                          fda.fda_set_id as fda_set_id,
                          ndc.name as ndc_code, 
                          cd.name as rxnorm_clinical_drug,
                          all_ingredients,
                          substring(ndc.name, 0, 5) as labeler
            MERGE (c:DataQualityConflict {
                conflict_id: fda_set_id + "_" + ndc_code
            })
            SET c.fda_drug_name = fda_drug_name,
                c.fda_set_id = fda_set_id,
                c.ndc_code = ndc_code,
                c.rxnorm_clinical_drug = rxnorm_clinical_drug,
                c.rxnorm_ingredients = all_ingredients,
                c.labeler = labeler,
                c.detected_at = $detected_at,
                c.status = "NEW",
                c.superseded_at = null
            RETURN count(c) as created
        """, detected_at=detected_at)
        
        created = result.single()["created"]
        print(f"Created {created} conflict records")
        
        # Get conflict type distribution
        result = session.run("""
            MATCH (c:DataQualityConflict) WHERE c.detected_at = $detected_at
            RETURN c.labeler as labeler, count(*) as count
            ORDER BY count DESC
            LIMIT 10
        """, detected_at=detected_at)
        
        print("")
        print("Top labelers with conflicts:")
        for row in result:
            print(f"  - Labeler {row['labeler']}: {row['count']} conflicts")
    
    driver.close()

def get_conflict_summary():
    """Get summary statistics for conflicts"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""
            MATCH (c:DataQualityConflict)
            WHERE c.superseded_at IS NULL
            RETURN count(c) as total_conflicts,
                   count(CASE WHEN c.status = 'NEW' THEN 1 END) as new_conflicts,
                   count(CASE WHEN c.status = 'ACKNOWLEDGED' THEN 1 END) as acknowledged,
                   count(CASE WHEN c.status = 'RESOLVED' THEN 1 END) as resolved
        """)
        stats = result.single()
        
        result = session.run("""
            MATCH (c:DataQualityConflict)
            WHERE c.superseded_at IS NULL
            RETURN c.labeler as labeler, count(*) as count
            ORDER BY count DESC
            LIMIT 5
        """)
        top_labelers = [dict(r) for r in result]
    
    driver.close()
    return {
        "total_conflicts": stats["total_conflicts"],
        "new_conflicts": stats["new_conflicts"],
        "acknowledged": stats["acknowledged"],
        "resolved": stats["resolved"],
        "top_labelers_with_conflicts": top_labelers
    }

if __name__ == "__main__":
    print("=" * 60)
    print("DATA QUALITY CONFLICT DETECTION")
    print("=" * 60)
    
    print("")
    print("1. Creating schema...")
    create_conflict_schema()
    
    print("")
    print("2. Detecting conflicts...")
    detect_and_store_conflicts()
    
    print("")
    print("3. Summary:")
    summary = get_conflict_summary()
    print(f"   Total active conflicts: {summary['total_conflicts']}")
    print(f"   New: {summary['new_conflicts']}")
    print(f"   Acknowledged: {summary['acknowledged']}")
    print(f"   Resolved: {summary['resolved']}")
