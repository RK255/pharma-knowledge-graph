import pandas as pd
from collections import defaultdict

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

# Paths for the output files
LAYER1_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_ROSETTA_2026-02-10.csv"
RELATIONSHIPS_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer0_to_Layer1_Relationships_ROSETTA_2026-02-10.csv"

def find_layer1_rosetta_stone():
    """
    The final script using the Rosetta Stone to decipher RXNREL.RRF.
    """
    print("--- Finding Layer 1 Nodes using the Rosetta Stone ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Scan RXNREL using the deciphered structure
    print(f"\nScanning {RXNREL_PATH} with the deciphered structure...")
    layer1_rxcuis = set()
    relationships = []
    relationship_counts = defaultdict(int)

    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            # We only care about lines with enough parts and where STYPE2 is CUI
            if len(parts) > 7 and parts[6] == 'CUI':
                # DECIPHERED INDICES
                rxcui1 = parts[0]   # The Layer 1 Node (e.g., BN)
                rela = parts[7]     # The descriptive relationship (e.g., has_tradename)
                rxcui2 = parts[4]   # Our Layer 0 Ingredient (e.g., IN)

                # Check if this relationship involves one of our ingredients as the target
                if rxcui2 in layer0_rxcuis:
                    relationship_counts[rela] += 1
                    
                    # Add the connected node to our set
                    layer1_rxcuis.add(rxcui1)
                    
                    # Store the relationship from our ingredient (L0) to the new node (L1)
                    relationships.append({
                        'rxcui_from': rxcui2,
                        'rxcui_to': rxcui1,
                        'relationship_type': rela
                    })

    print(f"✅ Found {len(layer1_rxcuis)} unique connected RxCUIs.")
    print(f"✅ Found {len(relationships)} relationships.")

    # 3. Look up details for the Layer 1 RxCUIs in RXNCONSO
    print(f"\nLooking up details for {len(layer1_rxcuis)} Layer 1 RxCUIs...")
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
    find_layer1_rosetta_stone()
