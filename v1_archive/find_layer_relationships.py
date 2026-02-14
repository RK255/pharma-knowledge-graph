import os
import csv
import sys

# --- Configuration ---
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_RXNORM_DIR = os.path.join(BASE_DIR, "data/raw_data")
IMPORT_CSV_DIR = os.path.join(BASE_DIR, "data/import_csvs")

def load_rxcuis_from_csv(filepath):
    """Loads RxCUIs from a CSV file into a set."""
    print(f"Loading RxCUIs from {os.path.basename(filepath)}...")
    rxcuis = set()
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader) # skip header
        for row in reader:
            if row and row[0]:
                rxcuis.add(row[0])
    print(f"✅ Loaded {len(rxcuis):,} RxCUIs.")
    return rxcuis

def main():
    """Finds all relationships between two layers."""
    layer1_file = os.path.join(IMPORT_CSV_DIR, "Layer1_Nodes.csv")
    layer2_file = os.path.join(IMPORT_CSV_DIR, "Layer2_Nodes.csv")
    
    if not os.path.exists(layer1_file) or not os.path.exists(layer2_file):
        print("❌ Error: Layer node files not found in import_csvs directory.")
        sys.exit(1)

    layer1_rxcuis = load_rxcuis_from_csv(layer1_file)
    layer2_rxcuis = load_rxcuis_from_csv(layer2_file)

    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    if not os.path.exists(rxnrel_path):
        print(f"❌ Error: RXNREL.RRF not found.")
        sys.exit(1)

    print("\nScanning RXNREL.RRF for relationships between layers...")
    relationships = []
    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]
            rxcui2 = parts[4]
            rel_type = parts[8]
            sab = parts[10]
            
            if sab != 'RXNORM': continue

            # Check for a connection from Layer 1 to Layer 2
            if rxcui1 in layer1_rxcuis and rxcui2 in layer2_rxcuis:
                relationships.append([rxcui1, rxcui2, rel_type, sab])
            # Or from Layer 2 to Layer 1
            elif rxcui2 in layer1_rxcuis and rxcui1 in layer2_rxcuis:
                relationships.append([rxcui1, rxcui2, rel_type, sab])

    print(f"✅ Found {len(relationships):,} relationships.")

    # --- Write the output file ---
    output_file = os.path.join(IMPORT_CSV_DIR, "Layer1_to_Layer2_Edges.csv")
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_rxcui', 'target_rxcui', 'relationship_type', 'source'])
        writer.writerows(relationships)
    
    print(f"\n✅ Relationship discovery complete! Wrote to {output_file}")

if __name__ == "__main__":
    main()
