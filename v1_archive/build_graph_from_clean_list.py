import os
import csv
import sys

# --- Configuration ---
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_RXNORM_DIR = os.path.join(BASE_DIR, "data/raw_data")
OUTPUT_DIR = os.path.join(BASE_DIR, "data/import_csvs")

def load_clean_ingredients(clean_file_path):
    """Loads the set of RxCUIs from our clean ingredient list."""
    print(f"Loading clean ingredient list from {os.path.basename(clean_file_path)}...")
    ingredient_rxcuis = set()
    with open(clean_file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) # skip header
        for row in reader:
            if row and row[0]:
                ingredient_rxcuis.add(row[0])
    print(f"✅ Loaded {len(ingredient_rxcuis):,} ingredients.")
    return ingredient_rxcuis

def main():
    """Builds a graph from a clean list of ingredients."""
    print("🌐 Welcome to the Simple Graph Builder!")
    
    clean_file = os.path.join(OUTPUT_DIR, "clean_layer0_ingredients.csv")
    if not os.path.exists(clean_file):
        print(f"❌ Error: Clean ingredient list not found at {clean_file}. Please run the helper script first.")
        sys.exit(1)
        
    ingredient_rxcuis = load_clean_ingredients(clean_file)
    
    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    if not os.path.exists(rxnrel_path):
        print(f"❌ Error: RXNREL.RRF not found at {rxnrel_path}.")
        sys.exit(1)
        
    print("Finding all connections for these ingredients in RXNREL.RRF...")
    edge_list = []
    connected_nodes = set()

    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]
            rxcui2 = parts[4]
            rela = parts[7]
            sab = parts[10]

            if sab != 'RXNORM': continue

            # If either side of the relationship is one of our ingredients, we keep it
            if rxcui1 in ingredient_rxcuis or rxcui2 in ingredient_rxcuis:
                edge_list.append([rxcui1, rxcui2, rela, sab])
                connected_nodes.add(rxcui1)
                connected_nodes.add(rxcui2)

    print(f"✅ Found {len(edge_list):,} total relationships.")
    
    # --- Write the output files ---
    print("\nWriting output files...")
    
    edge_output_file = os.path.join(OUTPUT_DIR, "Simple_Graph_Edges.csv")
    with open(edge_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_rxcui', 'target_rxcui', 'relationship_type', 'source'])
        writer.writerows(edge_list)
        
    node_output_file = os.path.join(OUTPUT_DIR, "Simple_Graph_Nodes.csv")
    with open(node_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rxcui'])
        for rxcui in sorted(list(connected_nodes)):
            writer.writerow([rxcui])

    print("\n✅ Simple graph discovery complete!")
    print(f"📄 Edge List: {edge_output_file}")
    print(f"📄 All Connected Nodes: {node_output_file}")

if __name__ == "__main__":
    main()
