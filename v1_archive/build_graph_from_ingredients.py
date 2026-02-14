import os
import csv
import sys
import zipfile

# --- Configuration ---
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_RXNORM_DIR = os.path.join(BASE_DIR, "data/raw_data")
OUTPUT_DIR = os.path.join(BASE_DIR, "data/import_csvs")

def load_layer0_ingredients(master_file_path):
    """Loads the set of RxCUIs for our Layer 0 ingredients."""
    print(f"Loading Layer 0 ingredients from {os.path.basename(master_file_path)}...")
    layer0_rxcuis = set()
    try:
        with open(master_file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if row and row[0]:
                    layer0_rxcuis.add(row[0])
        print(f"✅ Loaded {len(layer0_rxcuis):,} Layer 0 ingredients.")
        return layer0_rxcuis
    except FileNotFoundError:
        print(f"❌ Error: Master file not found at {master_file_path}")
        sys.exit(1)

def find_drugs_for_ingredients(layer0_ingredients, rxnrel_path):
    """Finds all drugs that have a 'has_ingredient' relationship with our Layer 0 ingredients."""
    print("Finding all drugs that contain Layer 0 ingredients using RXNREL.RRF...")
    drug_rxcuis = set()

    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]      # Col 1: Source RxCUI (the drug)
            rxcui2 = parts[4]      # Col 5: Target RxCUI (the ingredient)
            rela = parts[7]        # Col 8: Specific relationship label (e.g., 'has_ingredient')
            sab = parts[10]        # Col 11: Source (must be RXNORM)

            # We are looking for a 'has_ingredient' relationship from the RXNORM source
            # where the ingredient (rxcui2) is one of our Layer 0 ingredients.
            if sab == 'RXNORM' and rela == 'has_ingredient' and rxcui2 in layer0_ingredients:
                drug_rxcuis.add(rxcui1) # Add the drug (rxcui1) to our set
    print(f"✅ Found {len(drug_rxcuis):,} unique drugs that contain our ingredients.")
    return drug_rxcuis

def find_all_connections(drug_rxcuis, rxnrel_path):
    """Finds all relationships for the given list of drugs."""
    print("Finding all connections for those drugs using RXNREL.RRF...")
    all_connections = []
    connected_nodes = set()

    with open(rxnrel_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]
            rxcui2 = parts[1]
            rela = parts[2]
            sab = parts[7]

            # Only consider RXNORM source relationships
            if sab != 'RXNORM': continue

            # If either side of the relationship is one of our drugs, we keep it
            if rxcui1 in drug_rxcuis or rxcui2 in drug_rxcuis:
                all_connections.append([rxcui1, rxcui2, rela, sab])
                connected_nodes.add(rxcui1)
                connected_nodes.add(rxcui2)

    print(f"✅ Found {len(all_connections):,} total relationships.")
    return all_connections, connected_nodes

def main():
    """Main function to orchestrate the graph building process."""
    print("🌐 Welcome to the Graph Builder from Ingredients!")
    
    # --- Step 1: Find and load the master Layer 0 file ---
    merged_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('RxNorm') and 'merged_by_' in f and f.endswith('.csv')]
    if not merged_files:
        print("❌ No master merged file found. Please run the merge script first.")
        sys.exit(1)

    # Create a list of full paths to sort by modification time
    full_paths = [os.path.join(OUTPUT_DIR, f) for f in merged_files]
    full_paths.sort(key=os.path.getmtime, reverse=True)

    # Get the latest file's full path
    latest_merged_file = full_paths[0]
    
    layer0_ingredients = load_layer0_ingredients(latest_merged_file)

    # --- Step 2: Find the RxNorm files ---
    rxnorm_zip_files = [f for f in os.listdir(RAW_RXNORM_DIR) if f.startswith('RxNorm') and f.endswith('.zip')]
    rxnorm_zip_files.sort()
    latest_rxnorm_zip = os.path.join(RAW_RXNORM_DIR, rxnorm_zip_files[-1])
    
    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    if not os.path.exists(rxnrel_path):
        print(f"❌ Error: RXNREL.RRF not found at {rxnrel_path}. Please extract it from the RxNorm zip file.")
        sys.exit(1)

    # --- Step 3: Process the relationships ---
    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    drug_rxcuis = find_drugs_for_ingredients(layer0_ingredients, rxnrel_path)
    all_connections, connected_nodes = find_all_connections(drug_rxcuis, rxnrel_path)

    # --- Step 4: Write the output files ---
    print("\nWriting output files...")
    
    edge_output_file = os.path.join(OUTPUT_DIR, "Graph_Edges.csv")
    with open(edge_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_rxcui', 'target_rxcui', 'relationship_type', 'source'])
        writer.writerows(all_connections)
        
    node_output_file = os.path.join(OUTPUT_DIR, "Graph_Nodes.csv")
    with open(node_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rxcui'])
        for rxcui in sorted(list(connected_nodes)):
            writer.writerow([rxcui])

    print("\n✅ Graph discovery complete!")
    print(f"📄 Edge List: {edge_output_file}")
    print(f"📄 All Connected Nodes: {node_output_file}")

if __name__ == "__main__":
    main()
