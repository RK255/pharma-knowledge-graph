import pandas as pd
from collections import defaultdict

# --- Configuration ---
LAYER0_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
LAYER1_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_ROSETTA_2026-02-10.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

# Paths for the output files
LAYER2_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer2_Nodes_FILTERED_FINAL_2026-02-10.csv"
RELATIONSHIPS_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_to_Layer2_Relationships_FILTERED_FINAL_2026-02-10.csv"

def find_next_layer_filtered(source_paths, source_layer_names, next_layer_name):
    """
    Finds the next layer of nodes by mapping connections from given source layers,
    while filtering out any nodes already found in previous layers.
    """
    print(f"--- Finding {next_layer_name} Nodes (FILTERED) ---")

    # 1. Load all RxCUIs from previous layers to create a filter set
    print(f"Loading RxCUIs from previous layers to filter...")
    all_previous_rxcuis = set()
    for path, name in zip(source_paths, source_layer_names):
        df = pd.read_csv(path)
        # --- KEY FIX: Explicitly convert to string and update the set ---
        rxcuis = {str(rxcui) for rxcui in df['rxcui']}
        all_previous_rxcuis.update(rxcuis)
        print(f"  - Loaded {len(rxcuis)} from {name}")
    print(f"✅ Total RxCUIs to filter out: {len(all_previous_rxcuis)}")
    print(f"✅ Filter set data type is: {type(list(all_previous_rxcuis)[0])}")


    # 2. Scan RXNREL using the deciphered structure to find connections
    # We'll use Layer1 as the active source for this search
    print(f"\nScanning {RXNREL_PATH} for connections from Layer1...")
    layer1_df = pd.read_csv(LAYER1_NODES_PATH)
    source_rxcuis = {str(rxcui) for rxcui in layer1_df['rxcui']} # Also ensure source is strings

    next_layer_rxcuis = set()
    relationships = []
    relationship_counts = defaultdict(int)

    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) > 7 and parts[6] == 'CUI':
                rxcui1 = parts[0]
                rela = parts[7]
                rxcui2 = parts[4]

                # Check if this relationship involves one of our source nodes (Layer 1)
                is_source_to_next = (rxcui2 in source_rxcuis and rxcui1 not in source_rxcuis)
                is_next_to_source = (rxcui1 in source_rxcuis and rxcui2 not in source_rxcuis)

                if is_source_to_next or is_next_to_source:
                    # Determine which is the new node
                    next_rxcui = rxcui1 if is_source_to_next else rxcui2
                    
                    # --- THE KEY FILTER ---
                    # Only add the node if it hasn't been seen in ANY previous layer
                    # The comparison now works because both are strings
                    if next_rxcui not in all_previous_rxcuis:
                        relationship_counts[rela] += 1
                        next_layer_rxcuis.add(next_rxcui)
                        
                        # Store the relationship
                        from_rxcui = rxcui2 if is_source_to_next else rxcui1
                        to_rxcui = next_rxcui
                        relationships.append({
                            'rxcui_from': from_rxcui,
                            'rxcui_to': to_rxcui,
                            'relationship_type': rela
                        })

    print(f"✅ Found {len(next_layer_rxcuis)} unique {next_layer_name} RxCUIs after filtering.")
    print(f"✅ Found {len(relationships)} relationships.")

    # 3. Look up details for the new layer RxCUIs in RXNCONSO
    print(f"\nLooking up details for {len(next_layer_rxcuis)} {next_layer_name} RxCUIs...")
    next_layer_nodes = {} 
    
    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                rxcui, name, tty, sab = parts[0], parts[14], parts[12], parts[11]
                if rxcui in next_layer_rxcuis and sab == 'RXNORM':
                    if rxcui not in next_layer_nodes:
                        next_layer_nodes[rxcui] = {'name': name, 'tty': tty}
                        
    print(f"✅ Found details for {len(next_layer_nodes)} {next_layer_name} nodes.")

    # 4. OUTPUT RESULTS
    print(f"\n--- Distribution of {next_layer_name} Node Types (TTY) ---")
    tty_counts = defaultdict(int)
    for node in next_layer_nodes.values():
        tty_counts[node['tty']] += 1
    for tty, count in sorted(tty_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"TTY '{tty}': {count} nodes")

    print("\n--- Distribution of Relationship Types ---")
    for rela, count in sorted(relationship_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"Relationship '{rela}': {count} instances")

    # 5. Save files
    next_layer_df = pd.DataFrame.from_dict(next_layer_nodes, orient='index').reset_index()
    next_layer_df.rename(columns={'index': 'rxcui'}, inplace=True)
    next_layer_df.to_csv(LAYER2_NODES_PATH, index=False)
    print(f"\n✅ Saved {next_layer_name} nodes to {LAYER2_NODES_PATH}")

    rel_df = pd.DataFrame(relationships)
    rel_df.to_csv(RELATIONSHIPS_PATH, index=False)
    print(f"✅ Saved relationships to {RELATIONSHIPS_PATH}")

    print("\n--- Process Complete ---")

if __name__ == "__main__":
    # Call the function to find Layer 2, filtering out Layer 0 and Layer 1
    find_next_layer_filtered(
        source_paths=[LAYER0_CSV_PATH, LAYER1_NODES_PATH], 
        source_layer_names=["Layer0", "Layer1"],
        next_layer_name="Layer2"
    )
