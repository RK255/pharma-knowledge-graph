"""
Build Pharmacological Class Relationships from MeSH Data
=========================================================
Creates BELONGS_TO relationships between Ingredient nodes and 
PharmacologicalClass nodes based on mesh_pharm property.

Provenance Model:
- source: MeSH-Pharm (source database)
- source_type: PubChem_Enrichment (import method)
- citation: AMA-style citation for regulatory compliance
- retrieved_date: When data was fetched
- provenance_hash: Version identifier for audit trail
"""

from neo4j import GraphDatabase
import os
from datetime import datetime

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# Provenance configuration
PROVENANCE = {
    "source": "MeSH-Pharm",
    "source_type": "PubChem_Enrichment",
    "citation": "PubChem Compound Database. National Library of Medicine. https://pubchem.ncbi.nlm.nih.gov",
    "retrieved_date": datetime.now().strftime("%Y-%m-%d"),
    "provenance_hash": "mesh_pharm_pubchem_enrichment_v1"
}

def build_pharmacological_classes():
    """Create PharmacologicalClass nodes and BELONGS_TO relationships from mesh_pharm data."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # Step 1: Create PharmacologicalClass nodes with provenance
        print("Creating PharmacologicalClass nodes...")
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE i.mesh_pharm IS NOT NULL
            WITH i, split(i.mesh_pharm, '|') as classes
            UNWIND classes as class_name
            WITH trim(class_name) as class_name
            MERGE (c:PharmacologicalClass {name: class_name})
            SET c.source = 'MeSH-Pharm',
                c.citation = $citation,
                c.created_date = $retrieved_date
            RETURN count(DISTINCT c) as class_count
        """, PROVENANCE)
        class_count = result.single()['class_count']
        print(f"  Created/updated {class_count} PharmacologicalClass nodes with provenance")
        
        # Step 2: Create BELONGS_TO relationships with provenance
        print("Creating BELONGS_TO relationships with provenance...")
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE i.mesh_pharm IS NOT NULL
            WITH i, split(i.mesh_pharm, '|') as classes
            UNWIND classes as class_name
            WITH i, trim(class_name) as class_name
            MATCH (c:PharmacologicalClass {name: class_name})
            MERGE (i)-[r:BELONGS_TO]->(c)
            SET r.source = $source,
                r.source_type = $source_type,
                r.citation = $citation,
                r.retrieved_date = $retrieved_date,
                r.provenance_hash = $provenance_hash
            RETURN count(*) as rel_count
        """, PROVENANCE)
        rel_count = result.single()['rel_count']
        print(f"  Created {rel_count} BELONGS_TO relationships with provenance")
        
        # Step 3: Summary
        result = session.run("""
            MATCH (i:Ingredient)-[r:BELONGS_TO]->(c:PharmacologicalClass)
            RETURN count(DISTINCT i) as ingredients, 
                   count(DISTINCT c) as classes,
                   count(r) as relationships
        """)
        summary = result.single()
        print(f"\nSummary:")
        print(f"  {summary['ingredients']} ingredients")
        print(f"  {summary['classes']} pharmacological classes")
        print(f"  {summary['relationships']} relationships")
        print(f"\nProvenance: {PROVENANCE['citation']}")
    
    driver.close()
    return {"classes": class_count, "relationships": rel_count, "provenance": PROVENANCE}

if __name__ == "__main__":
    print("=" * 60)
    print("PHARMACOLOGICAL CLASS BUILDER (with Provenance)")
    print("=" * 60)
    build_pharmacological_classes()
