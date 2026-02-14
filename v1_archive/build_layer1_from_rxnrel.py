import os
import csv
import gzip
import sys

# --- Configuration ---
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_RXNORM_DIR = os.path.join(BASE_DIR, "data/raw_data")
OUTPUT_DIR = os.path.join(BASE_DIR, "data/import_csvs")

def load_layer0_nodes(master_file_path):
    """Loads the set of RxCUIs from our master Layer 0 file."""
    print(f"Loading Layer 0 nodes from {os.path.basename(master_file_path)}...")
    layer0_rxcuis = set()
    try:
        with open(master_file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                if row and row[0]: # Check if row and rxcui are not empty
                    layer0_rxcuis.add(row[0])
        print(f"✅ Loaded {len(layer0_rxcuis):,} Layer 0 nodes.")
        return layer0_rxcuis
    except FileNotFoundError:
        print(f"❌ Error: Master file not found at {master_file_path}")
        return None

def find_layer1_connections(layer0_rxcuis, rxnrel_file):
    """Parses RXNREL.RRF to find all connections to Layer 0 nodes."""
    print(f"Finding connections for Layer 0 nodes in {os.path.basename(rxnrel_file)}...")
    
    layer1_nodes = set()
    edge_list = []
    
    # RXNREL.RRF field indices
    rxcui1_idx = 0
    rxcui2_idx = 1
    rela_idx = 2
    sab_idx = 7

    with open(rxnrel_file, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) > 7:
                rxcui1 = parts[rxcui1_idx]
                rxcui2 = parts[rxcui2_idx]
                rela = parts[rela_idx]
                sab = parts[sab_idx]

                # Only consider relationships that come from the RXNORM source
                if sab != 'RXNORM':
                    continue

                # Check if this relationship involves one of our Layer 0 nodes
                if rxcui1 in layer0_rxcuis or rxcui2 in layer0_rxcuis:
                    edge_list.append([rxcui1, rxcui2, rela, sab])
                    
                    # Add the "other" node to our Layer 1 set
                    if rxcui1 in layer0_rxcuis:
                        layer1_nodes.add(rxcui2)
                    else:
                        layer1_nodes.add(rxcui1)
    
    print(f"✅ Found {len(layer1_nodes):,} unique Layer 1 nodes.")
    print(f"✅ Found {len(edge_list):,} total relationships.")
    return layer1_nodes, edge_list

def main():
    """Main function to orchestrate the process."""
    print("🌐 Welcome to the Layer 1 Graph Builder!")
    
    # --- Step 1: Find and select the master Layer 0 file ---
    def find_latest_merged_file():
        """Finds the most recently created master merged file."""
        try:
            all_files = os.listdir(OUTPUT_DIR)
            merged_files = [os.path.join(OUTPUT_DIR, f) for f in all_files if f.startswith('RxNorm') and 'merged_by_' in f and f.endswith('.csv')]
            if not merged_files:
                print("❌ No master merged file found. Please run the merge script first.")
                return None
            merged_files.sort(key=os.path.getmtime, reverse=True)
            return merged_files[0]
        except FileNotFoundError:
            print(f"❌ Error: The directory {OUTPUT_DIR} was not found.")
            return None

    master_file = find_latest_merged_file()
    if not master_file:
        sys.exit(1)
        
    layer0_rxcuis = load_layer0_nodes(master_file)
    if not layer0_rxcuis:
        sys.exit(1)

    # --- Step 2: Find the RXNREL.RRF file ---
    # Find the most recent RxNorm zip to get the RXNREL.RRF
    rxnorm_dir = os.path.join(RAW_RXNORM_DIR, "extracted_rrf") # Updated to look in the extracted folder
    
    rxnrel_files = [f for f in os.listdir(rxnorm_dir) if f.startswith('RXNREL') and f.endswith('.RRF')]
    if not rxnrel_files:
        print(f"❌ Error: No RXNREL.RRF file found in {rxnorm_dir}.")
        return
    rxnrel_path = os.path.join(rxnorm_dir, rxnrel_files[0])
    
    # --- Step 3: Process the relationships ---
    layer1_nodes, edge_list = find_layer1_connections(layer0_rxcuis, rxnrel_path)

    # --- Step 4: Write the output files ---
    print("\nWriting output files...")
    
    # Write the edge list
    edge_output_file = os.path.join(OUTPUT_DIR, "Layer0_to_Layer1_Edges.csv")
    with open(edge_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_rxcui', 'target_rxcui', 'relationship_type', 'source'])
        writer.writerows(edge_list)
        
    # Write the list of new Layer 1 nodes
    node_output_file = os.path.join(OUTPUT_DIR, "Layer1_Nodes.csv")
    with open(node_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rxcui'])
        for rxcui in sorted(list(layer1_nodes)):
            writer.writerow([rxcui])

    print("\n✅ Layer 1 discovery complete!")
    print(f"📄 Edge List: {edge_output_file}")
    print(f"📄 Layer 1 Nodes: {node_output_file}")

if __name__ == "__main__":
    main()
