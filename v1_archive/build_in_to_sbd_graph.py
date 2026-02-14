import os
import csv
import sys

# --- Configuration ---
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_RXNORM_DIR = os.path.join(BASE_DIR, "data/raw_data")
OUTPUT_DIR = os.path.join(BASE_DIR, "data/import_csvs")

def load_layer0_rxcuis(clean_file_path):
    """Loads the set of RxCUIs from our clean ingredient list."""
    print(f"Loading Layer 0 ingredients from {os.path.basename(clean_file_path)}...")
    layer0_rxcuis = set()
    with open(clean_file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) # skip header
        for row in reader:
            if row and row[0]:
                layer0_rxcuis.add(row[0])
    print(f"✅ Loaded {len(layer0_rxcuis):,} Layer 0 ingredients.")
    return layer0_rxcuis

def main():
    """Builds a clean graph connecting Layer 0 (IN) to Layer 1 (SBD)."""
    print("🏗️  Building the Clean IN-to-SBD Graph!")
    
    clean_file = os.path.join(OUTPUT_DIR, "clean_layer0_ingredients.csv")
    if not os.path.exists(clean_file):
        print(f"❌ Error: Clean ingredient list not found at {clean_file}. Please run the helper script first.")
        sys.exit(1)
        
    layer0_rxcuis = load_layer0_rxcuis(clean_file)
    
    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    if not os.path.exists(rxnrel_path):
        print(f"❌ Error: RXNREL.RRF not found at {rxnrel_path}.")
        sys.exit(1)

    # --- Step 1: Find all SBDs connected to our ingredients using RXNREL.RRF ---
    print("\nFinding all SBDs connected to our ingredients using RXNREL.RRF...")
    layer1_sbd_rxcuis = set()
    edge_list = []

    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]      # Source RxCUI (the potential SBD)
            rxcui2 = parts[4]      # Target RxCUI (our ingredient)
            rela = parts[7]        # Relationship label
            sab = parts[10]        # Source

            if sab == 'RXNORM' and rela == 'ingredient_of' and rxcui2 in layer0_rxcuis:
                layer1_sbd_rxcuis.add(rxcui1)
                edge_list.append([rxcui1, rxcui2, 'has_ingredient', 'RXNORM'])
                
    print(f"✅ Found {len(layer1_sbd_rxcuis):,} unique SBDs in Layer 1.")
    print(f"✅ Found {len(edge_list):,} relationships between Layer 0 and Layer 1.")

    # --- Step 2: Write the clean output files ---
    print("\nWriting clean graph files...")
    
    edge_output_file = os.path.join(OUTPUT_DIR, "Layer0_IN_to_Layer1_SBD_Edges.csv")
    with open(edge_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_sbd_rxcui', 'target_in_rxcui', 'relationship_type', 'source'])
        writer.writerows(edge_list)
        
    node_output_file = os.path.join(OUTPUT_DIR, "Layer1_SBD_Nodes.csv")
    with open(node_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rxcui'])
        for rxcui in sorted(list(layer1_sbd_rxcuis)):
            writer.writerow([rxcui])

    print("\n✅ Clean IN-to-SBD graph discovery complete!")
    print(f"📄 Edge List (SBD -> IN): {edge_output_file}")
    print(f"📄 Layer 1 SBD Nodes: {node_output_file}")

if __name__ == "__main__":
    main()
