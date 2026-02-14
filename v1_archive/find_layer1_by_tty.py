import pandas as pd
from collections import defaultdict

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

# Define the TTY codes we want to find as Layer 1 nodes
TTY_FILTER = ['GPCK', 'BPCK', 'SCD', 'SBD', 'MIN', 'IN', 'PIN', 'BN', 'DF']

# Paths for the output files
LAYER1_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_by_TTY_2026-02-10.csv"
RELATIONSHIPS_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer0_to_Layer1_Relationships_by_TTY_2026-02-10.csv"

def find_layer1_by_tty():
    """
    Finds Layer 1 nodes by first identifying all RxCUIs with desired TTYs,
    then finding relationships from Layer 0 to that set.
    """
    print("--- Finding Layer 1 Nodes by TTY Filter ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Build a map of all RxCUIs that have our desired TTYs
    print(f"\nBuilding map of all concepts with TTY in {TTY_FILTER} from {RXNCONSO_PATH}...")
    valid_target_rxcuis = set()
    
    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                rxcui, tty, sab = parts[0], parts[12], parts[11]
                if sab == 'RXNORM' and tty in TTY_FILTER:
                    valid_target_rxcuis.add(rxcui)

    print(f"✅ Found {len(valid_target_rxcuis)} concepts with the desired TTYs.")

    # 3. Scan RXNREL to find relationships between Layer 0 and our valid targets
    print(f"\nScanning {RXNREL_PATH} for relationships...")
    layer1_nodes = {}
    relationships = []
    relationship_counts = defaultdict(int)

    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 9:
                rxcui1, rela, rxcui2 = parts[4], parts[7], parts[8]

                # Check if this relationship connects a Layer 0 ingredient to a valid target
                is_l0_to_target = (rxcui1 in layer0_rxcuis and rxcui2 in valid_target_rxcuis)
                is_target_to_l0 = (rxcui2 in layer0_rxcuis and rxcui1 in valid_target_rxcuis)

                if is_l0_to_target or is_target_to_l0:
                    relationship_counts[rela] += 1
                    
                    # Determine which is the target node and store it
                    target_rxcui = rxcui2 if is_l0_to_target else rxcui1
                    if target_rxcui not in layer1_nodes:
                        # We need to look up its name and TTY
                        with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f_conso:
                            for line_conso in f_conso:
                                con_parts = line_conso.strip().split('|')
                                if len(con_parts) >= 18 and con_parts[0] == target_rxcui:
                                    if con_parts[11] == 'RXNORM':
                                        layer1_nodes[target_rxcui] = {
                                            'name': con_parts[14], 
                                            'tty': con_parts[12]
                                        }
                                        break # Found it, no need to keep searching

                    # Store the relationship
                    relationships.append({
                        'rxcui_from': rxcui1,
                        'rxcui_to': rxcui2,
                        'relationship_type': rela
                    })

    print(f"✅ Found {len(layer1_nodes)} unique Layer 1 nodes.")
    print(f"✅ Found {len(relationships)} relationships.")

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
    find_layer1_by_tty()
