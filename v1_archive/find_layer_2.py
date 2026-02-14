import os
import csv
import sys

# --- Configuration ---
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_RXNORM_DIR = os.path.join(BASE_DIR, "data/raw_data")

def load_existing_rxcuis(layer0_file, layer1_file):
    """Loads RxCUIs from our existing layers."""
    print("Loading existing RxCUIs...")
    existing_rxcuis = set()
    for filepath in [layer0_file, layer1_file]:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader) # skip header
            for row in reader:
                if row and row[0]:
                    existing_rxcuis.add(row[0])
    print(f"✅ Loaded {len(existing_rxcuis):,} existing RxCUIs.")
    return existing_rxcuis

def main():
    """Finds the next layer of connected nodes."""
    layer0_file = os.path.join(BASE_DIR, "data/import_csvs/clean_layer0_ingredients.csv")
    layer1_file = os.path.join(BASE_DIR, "data/import_csvs/Layer1_Nodes.csv") # You will create this file
    
    if not os.path.exists(layer1_file):
        print(f"❌ Error: Layer 1 file not found at {layer1_file}. Please export it from Neo4j first.")
        sys.exit(1)
        
    existing_rxcuis = load_existing_rxcuis(layer0_file, layer1_file)
    
    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    if not os.path.exists(rxnrel_path):
        print(f"❌ Error: RXNREL.RRF not found.")
        sys.exit(1)

    print("\nScanning RXNREL.RRF for new connections...")
    next_layer_rxcuis = set()
    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]
            rxcui2 = parts[4]
            sab = parts[10]
            
            if sab != 'RXNORM': continue

            # If one node is in our existing set, add the other to the new set
            if rxcui1 in existing_rxcuis and rxcui2 not in existing_rxcuis:
                next_layer_rxcuis.add(rxcui2)
            elif rxcui2 in existing_rxcuis and rxcui1 not in existing_rxcuis:
                next_layer_rxcuis.add(rxcui1)

    print(f"✅ Found {len(next_layer_rxcuis):,} new RxCUIs for the next layer.")

    # --- Write the output file ---
    output_file = os.path.join(BASE_DIR, "data/import_csvs/Layer2_Nodes.csv")
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rxcui'])
        for rxcui in sorted(list(next_layer_rxcuis)):
            writer.writerow([rxcui])
    
    print(f"\n✅ Layer 2 discovery complete! Wrote to {output_file}")

if __name__ == "__main__":
    main()
