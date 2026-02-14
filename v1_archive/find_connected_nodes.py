import pandas as pd
from neo4j import GraphDatabase

# Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your_password"  # Replace with your actual password

# Path to your merged data file
MERGED_DATA_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"

def find_connected_nodes():
    """Find all nodes connected to the ingredient nodes"""
    
    # Load the ingredient data
    print("Loading ingredient data...")
    ingredients_df = pd.read_csv(MERGED_DATA_PATH)
    ingredient_rxcuis = ingredients_df['rxcui'].tolist()
    
    # Connect to Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # First, let's verify our ingredient nodes exist
        result = session.run(
            "MATCH (n:Ingredient) WHERE n.rxcui IN $rxcuis RETURN count(n) as count",
            rxcuis=ingredient_rxcuis
        )
        count = result.single()["count"]
        print(f"Found {count} ingredient nodes in the graph")
        
        # Find all nodes connected to our ingredients
        print("Finding all connected nodes...")
        query = """
        MATCH (i:Ingredient)-[]-(connected)
        WHERE i.rxcui IN $rxcuis
        WITH DISTINCT connected
        RETURN labels(connected) as labels, count(connected) as count
        ORDER BY count DESC
        """
        
        result = session.run(query, rxcuis=ingredient_rxcuis)
        
        print("\nConnected node types and counts:")
        for record in result:
            labels = record["labels"]
            count = record["count"]
            print(f"{labels}: {count}")
        
        # Get a sample of connected nodes for each type
        print("\nSample connected nodes:")
        query = """
        MATCH (i:Ingredient)-[]-(connected)
        WHERE i.rxcui IN $rxcuis
        WITH DISTINCT connected, labels(connected) as labels
        RETURN connected.rxcui as rxcui, connected.name as name, labels
        LIMIT 20
        """
        
        result = session.run(query, rxcuis=ingredient_rxcuis)
        
        for record in result:
            rxcui = record["rxcui"]
            name = record["name"]
            labels = record["labels"]
            print(f"RxCUI: {rxcui}, Name: {name}, Labels: {labels}")
    
    driver.close()

if __name__ == "__main__":
    find_connected_nodes()
