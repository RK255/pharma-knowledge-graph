import pandas as pd
from collections import defaultdict

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

# Paths for the output files
LAYER1_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_TRULY_FINAL_2026-02-10.csv"
RELATIONSHIPS_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer0_to_Layer1_Relationships_TRULY_FINAL_2026-02-10.csv"

def find_layer1_truly_final():
    """
    The FINAL, CORRECT method with the correct column indices.
    """
    print("--- Finding Layer 1 Nodes with CORRECT Column Indices ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Scan RXNREL and find all connected RxCUIs
    print(f"\nScanning {RXNREL_PATH} with correct indices...")
    all_involved_rxcuis = set()
    relationships = []
    relationship_counts = defaultdict(int)

    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 9:
                # CORRECTED INDICES BASED ON YOUR DISCOVERY
                rxcui1 = parts[4]   # Column 5
                rela = parts[7]     # Column 8
                rxcui2 = parts[5]   # Column 6 - THIS IS THE KEY FIX

                # Check if this relationship involves one of our ingredients
                if rxcui1 in layer0_rxcuis or rxcui2 in layer0_rxcuis:
                    relationship_counts[rela] += 1
                    
                    # Add BOTH sides of the relationship to our set
                    all_involved_rxcuis.add(rxcui1)
                    all_involved_rxcuis.add(rxcui2)
                    
                    # Store the relationship
                    relationships.append({
                        'rxcui_from': rxcui1,
                        'rxcui_to': rxcui2,
                        'relationship_type': rela
                    })

    print(f"✅ Found {len(all_involved_rxcuis)} total RxCUIs involved in {len(relationships)} relationships.")

    # 3. SUBTRACT Layer 0 to get Layer 1
    layer1_rxcuis = all_involved_rxcuis - layer0_rxcuis
    print(f"✅ After subtracting Layer 0, we have {len(layer1_rxcuis)} unique Layer 1 RxCUIs.")

    # 4. Look up details for the Layer 1 RxCUIs in RXNCONSO
    print(f"\nLooking up details for {len(layer1_rxcuis)} Layer 1 RxCUIs in {RXNCONSO_PATH}...")
    layer1_nodes = {} # {rxcui: {'name': name, 'tty': tty}}
    
    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                rxcui, name, tty, sab = parts[0], parts[14], parts[12], parts[11]
                if rxcui in layer1_rxcuis and sab == 'RXNORM':
                    if rxcui not in layer1_nodes:
                        layer1_nodes[rxcui] = {'name': name, 'tty': tty}
                        
    print(f"✅ Found details for {len(layer1_nodes)} Layer 1 nodes.")

    # 5. OUTPUT RESULTS
    print("\n--- Distribution of Layer 1 Node Types (TTY) ---")
    tty_counts = defaultdict(int)
    for node in layer1_nodes.values():
        tty_counts[node['tty']] += 1
    for tty, count in sorted(tty_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"TTY '{tty}': {count} nodes")

    print("\n--- Distribution of Relationship Types ---")
    for rela, count in sorted(relationship_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"Relationship '{rela}': {count} instances")

    # 6. Save files
    layer1_df = pd.DataFrame.from_dict(layer1_nodes, orient='index').reset_index()
    layer1_df.rename(columns={'index': 'rxcui'}, inplace=True)
    layer1_df.to_csv(LAYER1_NODES_PATH, index=False)
    print(f"\n✅ Saved Layer 1 nodes to {LAYER1_NODES_PATH}")

    rel_df = pd.DataFrame(relationships)
    rel_df.to_csv(RELATIONSHIPS_PATH, index=False)
    print(f"✅ Saved relationships to {RELATIONSHIPS_PATH}")

    print("\n--- Process Complete ---")

if __name__ == "__main__":
    find_layer1_truly_final()
