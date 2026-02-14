import os
import csv
import sys

# --- Configuration ---
BASE_DIR = "/mnt/fast_raid/server_projects/Geo/graph_workshop"
RAW_RXNORM_DIR = os.path.join(BASE_DIR, "data/raw_data")
OUTPUT_DIR = os.path.join(BASE_DIR, "data/import_csvs")

def load_rxcuis_from_file(filepath):
    """Loads a set of RxCUIs from a simple CSV file."""
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
    """Assembles the final graph from Layer 0 and Layer 1 nodes."""
    print("🧩 Assembling the Final Graph for Plotting!")
    
    # --- Step 1: Load our two layers of nodes ---
    layer0_file = os.path.join(OUTPUT_DIR, "clean_layer0_ingredients.csv")
    layer1_file = os.path.join(OUTPUT_DIR, "Layer1_SBD_Nodes.csv")

    if not os.path.exists(layer0_file) or not os.path.exists(layer1_file):
        print("❌ Error: Layer 0 or Layer 1 node files not found. Please run the previous scripts first.")
        sys.exit(1)

    layer0_rxcuis = load_rxcuis_from_file(layer0_file)
    layer1_rxcuis = load_rxcuis_from_file(layer1_file)
    
    # Combine them into one master set of all nodes in our graph
    all_graph_nodes = layer0_rxcuis.union(layer1_rxcuis)
    print(f"✅ Total nodes in final graph: {len(all_graph_nodes):,}")

    # --- Step 2: Find all relationships between these nodes ---
    print("\nFinding all relationships between these nodes in RXNREL.RRF...")
    rxnrel_path = os.path.join(RAW_RXNORM_DIR, "extracted_rrf", "RXNREL.RRF")
    if not os.path.exists(rxnrel_path):
        print(f"❌ Error: RXNREL.RRF not found at {rxnrel_path}.")
        sys.exit(1)

    final_edge_list = []
    with open(rxnrel_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 9: continue
            
            rxcui1 = parts[0]
            rxcui2 = parts[4]
            rela = parts[7]
            sab = parts[10]

            if sab != 'RXNORM': continue

            # We only care about relationships where BOTH nodes are in our graph
            if rxcui1 in all_graph_nodes and rxcui2 in all_graph_nodes:
                final_edge_list.append([rxcui1, rxcui2, rela, sab])
                
    print(f"✅ Found {len(final_edge_list):,} relationships for our final graph.")

    # --- Step 3: Write the final, clean output files ---
    print("\nWriting final graph files...")
    
    edge_output_file = os.path.join(OUTPUT_DIR, "Final_Graph_Edges.csv")
    with open(edge_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['source_rxcui', 'target_rxcui', 'relationship_type', 'source'])
        writer.writerows(final_edge_list)
        
    node_output_file = os.path.join(OUTPUT_DIR, "Final_Graph_Nodes.csv")
    with open(node_output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rxcui'])
        for rxcui in sorted(list(all_graph_nodes)):
            writer.writerow([rxcui])

    print("\n✅ Final graph assembly complete!")
    print(f"📄 Final Edge List: {edge_output_file}")
    print(f"📄 Final Node List: {node_output_file}")
    print("\nThese files are ready to be imported into a graph visualization tool.")

if __name__ == "__main__":
    main()
