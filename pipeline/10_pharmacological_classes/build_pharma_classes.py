"""
Build Pharmacological Class Relationships from MeSH Data
=========================================================
Creates BELONGS_TO relationships between Ingredient nodes and 
PharmacologicalClass nodes based on mesh_pharm property.

Run this during ingestion to establish drug-class relationships.
"""

from neo4j import GraphDatabase
import os

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Nani*48301")

def build_pharmacological_classes():
    """Create PharmacologicalClass nodes and BELONGS_TO relationships from mesh_pharm data."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # Step 1: Create PharmacologicalClass nodes
        print("Creating PharmacologicalClass nodes...")
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE i.mesh_pharm IS NOT NULL
            WITH i, split(i.mesh_pharm, '|') as classes
            UNWIND classes as class_name
            WITH trim(class_name) as class_name
            MERGE (c:PharmacologicalClass {name: class_name})
            SET c.source = 'MeSH-Pharm'
            RETURN count(DISTINCT c) as class_count
        """)
        class_count = result.single()['class_count']
        print(f"  Created/updated {class_count} PharmacologicalClass nodes")
        
        # Step 2: Create BELONGS_TO relationships
        print("Creating BELONGS_TO relationships...")
        result = session.run("""
            MATCH (i:Ingredient)
            WHERE i.mesh_pharm IS NOT NULL
            WITH i, split(i.mesh_pharm, '|') as classes
            UNWIND classes as class_name
            WITH i, trim(class_name) as class_name
            MATCH (c:PharmacologicalClass {name: class_name})
            MERGE (i)-[:BELONGS_TO]->(c)
            RETURN count(*) as rel_count
        """)
        rel_count = result.single()['rel_count']
        print(f"  Created {rel_count} BELONGS_TO relationships")
        
        # Summary
        result = session.run("""
            MATCH (i:Ingredient)-[:BELONGS_TO]->(c:PharmacologicalClass)
            RETURN count(DISTINCT i) as ingredients, count(DISTINCT c) as classes
        """)
        summary = result.single()
        print(f"\nSummary: {summary['ingredients']} ingredients classified into {summary['classes']} classes")
    
    driver.close()
    return {"classes": class_count, "relationships": rel_count}

if __name__ == "__main__":
    print("=" * 60)
    print("PHARMACOLOGICAL CLASS BUILDER")
    print("=" * 60)
    build_pharmacological_classes()
