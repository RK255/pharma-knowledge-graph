import pandas as pd
from collections import defaultdict

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

# Paths for the output files
LAYER1_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_from_RXNREL_2026-02-10.csv"
RELATIONSHIPS_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer0_to_Layer1_Relationships_from_RXNREL_2026-02-10.csv"

def find_layer1_from_rxnrel():
    """
    Finds Layer 1 nodes and relationships by scanning RXNREL.RRF.
    """
    print("--- Finding Layer 1 Nodes and Relationships from RXNREL.RRF ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Scan RXNREL to find all connected RxCUIs
    print(f"\nScanning {RXNREL_PATH} to find connected nodes...")
    connected_rxcuis = set()
    relationships = []
    relationship_counts = defaultdict(int)

    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            # RXNREL has at least 8 columns, we care about 4, 6, 7
            if len(parts) >= 8:
                rxcui1 = parts[4]
                rela = parts[6]
                rxcui2 = parts[7]

                # Check if this relationship involves one of our ingredients
                if rxcui1 in layer0_rxcuis or rxcui2 in layer0_rxcuis:
                    relationship_counts[rela] += 1
                    
                    # Determine which RxCUI is our ingredient and which is the connected node
                    if rxcui1 in layer0_rxcuis:
                        from_rxcui = rxcui1
                        to_rxcui = rxcui2
                    else:
                        from_rxcui = rxcui2
                        to_rxcui = rxcui1
                    
                    # Add the connected node to our set (unless it's another ingredient)
                    if to_rxcui not in layer0_rxcuis:
                        connected_rxcuis.add(to_rxcui)
                    
                    # Store the relationship
                    relationships.append({
                        'rxcui_from': from_rxcui,
                        'rxcui_to': to_rxcui,
                        'relationship_type': rela
                    })

    print(f"✅ Found {len(connected_rxcuis)} unique connected RxCUIs.")
    print(f"✅ Found {len(relationships)} relationships.")

    # 3. Look up details for the connected RxCUIs in RXNCONSO
    print(f"\nLooking up details for {len(connected_rxcuis)} connected RxCUIs in {RXNCONSO_PATH}...")
    layer1_nodes = {} # {rxcui: {'name': name, 'tty': tty}}
    
    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                rxcui, name, tty, sab = parts[0], parts[14], parts[12], parts[11]
                if rxcui in connected_rxcuis and sab == 'RXNORM':
                    # We found an active RxNorm entry for a connected node
                    if rxcui not in layer1_nodes: # Only take the first one we find
                        layer1_nodes[rxcui] = {'name': name, 'tty': tty}
                        
    print(f"✅ Found details for {len(layer1_nodes)} connected nodes.")

    # 4. OUTPUT RESULTS
    print("\n--- Distribution of Layer 1 Node Types (TTY) ---")
    tty_counts = defaultdict(int)
    for node in layer1_nodes.values():
        tty_counts[node['tty']] += 1
    for tty, count in sorted(tty_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"TTY '{tty}': {count} nodes")

    print("\n--- Distribution of Relationship Types ---")
    for rela, count in sorted(relationship_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"Relationship '{rela}': {count} instances")

    # 5. Save files
    layer1_df = pd.DataFrame.from_dict(layer1_nodes, orient='index').reset_index()
    layer1_df.rename(columns={'index': 'rxcui'}, inplace=True)
    layer1_df.to_csv(LAYER1_NODES_PATH, index=False)
    print(f"\n✅ Saved Layer 1 nodes to {LAYER1_NODES_PATH}")

    rel_df = pd.DataFrame(relationships)
    rel_df.to_csv(RELATIONSHIPS_PATH, index=False)
    print(f"✅ Saved relationships to {RELATIONSHIPS_PATH}")

    print("\n--- Process Complete ---")

if __name__ == "__main__":
    find_layer1_from_rxnrel()
