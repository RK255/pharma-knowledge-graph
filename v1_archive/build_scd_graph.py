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
    """Builds a clean graph connecting Layer 0 (IN) to Layer 1 (SCD)."""
    print("🏗️  Building the Clean IN-to-SCD Graph!")
    
    clean_file = os.path.join(OUTPUT_DIR, "clean_layer0_ingredients.csv")
    if not os.path.exists(clean_file):
        print(f"❌ Error: Clean ingredient list not found at {clean_file}. Please run the helper script first.")
        sys.exit(1)
        
    layer0_rxcuis = load_layer0_rxcuis(clean_file)
    
    # --- Step 1: Find all SCDs connected to our ingredients using RXNREL.RRF ---
    print("\nFinding all SCDs connected to our ingredients using RXNREL.RRF...")
    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    if not os.path.exists(rxnrel_path):
        print(f"❌ Error: RXNREL.RRF not found at {rxnrel_path}.")
        sys.exit(1)

    potential_scd_rxcuis = set()
    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]      # Source RxCUI (the potential drug)
            rxcui2 = parts[4]      # Target RxCUI (our ingredient)
            rela = parts[7]        # Relationship label
            sab = parts[10]        # Source

            if sab == 'RXNORM' and rela == 'ingredient_of' and rxcui2 in layer0_rxcuis:
                potential_scd_rxcuis.add(rxcui1)
    
    print(f"✅ Found {len(potential_scd_rxcuis):,} potential drug RxCUIs connected to our ingredients.")

    # --- Step 2: Filter that list to find only the ones with TTY='SCD' ---
    print("\nFiltering for only Semantic Clinical Drugs (TTY='SCD')...")
    rxnconso_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNCONSO.RRF")
    if not os.path.exists(rxnconso_path):
        print(f"❌ Error: RXNCONSO.RRF not found at {rxnconso_path}.")
        sys.exit(1)

    layer1_scd_rxcuis = set()
    edge_list = []
    with open(rxnconso_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 14: continue
            
            rxcui = parts[0]
            tty = parts[12]
            source = parts[11]

            if source == 'RXNORM' and tty == 'SCD' and rxcui in potential_scd_rxcuis:
                layer1_scd_rxcuis.add(rxcui)
    
    print(f"✅ Confirmed {len(layer1_scd_rxcuis):,} of these are SCDs for our Layer 1.")

    # --- Step 3: Build the final edge list ---
    print("\nBuilding the final edge list between SCDs and INs...")
    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]
            rxcui2 = parts[4]
            rela = parts[7]
            sab = parts[10]

            if sab == 'RXNORM' and rela == 'ingredient_of' and rxcui1 in layer1_scd_rxcuis:
                edge_list.append([rxcui1, rxcui2, 'has_ingredient', 'RXNORM'])

    print(f"✅ Found {len(edge_list):,} relationships between Layer 0 and Layer 1.")

    # --- Step 4: Write the clean output files ---
    print("\nWriting clean graph files...")
    
    edge_output_file = os.path.join(OUTPUT_DIR, "Layer0_IN_to_Layer1_SCD_Edges.csv")
    with open(edge_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_scd_rxcui', 'target_in_rxcui', 'relationship_type', 'source'])
        writer.writerows(edge_list)
        
    node_output_file = os.path.join(OUTPUT_DIR, "Layer1_SCD_Nodes.csv")
    with open(node_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rxcui'])
        for rxcui in sorted(list(layer1_scd_rxcuis)):
            writer.writerow([rxcui])

    print("\n✅ Clean IN-to-SCD graph discovery complete!")
    print(f"📄 Edge List (SCD -> IN): {edge_output_file}")
    print(f"📄 Layer 1 SCD Nodes: {node_output_file}")

if __name__ == "__main__":
    main()
