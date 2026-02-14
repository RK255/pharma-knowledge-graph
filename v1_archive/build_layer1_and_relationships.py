import pandas as pd
from collections import defaultdict

# --- Configuration ---
# Path to your clean, enriched ingredient list (Layer 0)
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"

# Path to the raw RxNorm files
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

# Paths for the output files
LAYER1_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_2026-02-10.csv"
RELATIONSHIPS_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer0_to_Layer1_Relationships_2026-02-10.csv"

def build_layer1_and_relationships():
    """
    Step 1: Finds all Layer 1 nodes connected to Layer 0 ingredients via name matching in RXNCONSO.
    Step 2: Finds the explicit relationships between Layer 0 and Layer 1 in RXNREL.
    """
    print("--- Building Layer 1 and Finding Relationships ---")

    # --- STEP 1: FIND LAYER 1 NODES ---
    print("\n--- STEP 1: Finding Layer 1 Nodes via RXNCONSO.RRF ---")
    
    # 1. Load our Layer 0 ingredients and their names
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    ingredient_map = dict(zip(ingredients_df['rxcui'].astype(str), ingredients_df['ingredient_name']))
    layer0_rxcuis = set(ingredient_map.keys())
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Build a map of all normalized names to their RxCUIs from RXNCONSO.RRF
    print(f"Building name-to-RxCui map from {RXNCONSO_PATH}...")
    name_to_rxcuis = defaultdict(set)
    
    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                # CORRECTED: The name (STR) is in column 14 (index 13)
                # CORRECTED: We are no longer reading the 'suppress' field
                rxcui, name, tty, sab = parts[0], parts[14], parts[12], parts[11]
                
                # CORRECTED: Removed the suppress check, just check the source
                if sab == 'RXNORM':
                    normalized_name = name.lower()
                    name_to_rxcuis[normalized_name].add(rxcui)

    print(f"✅ Built map for {len(name_to_rxcuis)} unique normalized names.")

    print("\nFinding Layer 1 concepts by name...")
    layer1_nodes = {}  # {rxcui: {'name': name, 'tty': tty}}
    
    for rxcui, name in ingredient_map.items():
        normalized_name = name.lower()
        if normalized_name in name_to_rxcuis:
            for connected_rxcui in name_to_rxcuis[normalized_name]:
                if connected_rxcui == rxcui: continue

                if connected_rxcui not in layer1_nodes:
                    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f_conso:
                        for line in f_conso:
                            con_parts = line.strip().split('|')
                            if len(con_parts) >= 18 and con_parts[0] == connected_rxcui:
                                if con_parts[11] == 'RXNORM':
                                    # CORRECTED: The name (STR) is in column 14 (index 13)
                                    layer1_nodes[connected_rxcui] = {
                                        'name': con_parts[13], 
                                        'tty': con_parts[12]
                                    }
                                    break
    
    print(f"✅ Found {len(layer1_nodes)} unique Layer 1 nodes.")

    # 3. Find all Layer 1 RxCUIs and their details
    print("\nFinding Layer 1 concepts by name...")
    layer1_nodes = {}  # {rxcui: {'name': name, 'tty': tty}}
    
    for rxcui, name in ingredient_map.items():
        normalized_name = name.lower()
        if normalized_name in name_to_rxcuis:
            for connected_rxcui in name_to_rxcuis[normalized_name]:
                if connected_rxcui == rxcui: continue # Skip self

                if connected_rxcui not in layer1_nodes:
                    # Look up details for this connected RxCUI
                    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f_conso:
                        for line in f_conso:
                            con_parts = line.strip().split('|')
                            if len(con_parts) >= 18 and con_parts[0] == connected_rxcui:
                                if con_parts[11] == 'RXNORM' and con_parts[17] == 'N':
                                    layer1_nodes[connected_rxcui] = {
                                        'name': con_parts[14], 
                                        'tty': con_parts[12]
                                    }
                                    break
    
    print(f"✅ Found {len(layer1_nodes)} unique Layer 1 nodes.")

    # --- STEP 2: FIND RELATIONSHIPS ---
    print("\n--- STEP 2: Finding Relationships in RXNREL.RRF ---")
    
    layer1_rxcuis = set(layer1_nodes.keys())
    relationships = []
    relationship_counts = defaultdict(int)

    print(f"Scanning {RXNREL_PATH} for relationships between Layer 0 and Layer 1...")
    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 8:
                rxcui1, rela, rxcui2 = parts[4], parts[7], parts[6]

                # Check if this relationship connects a Layer 0 node to a Layer 1 node
                is_l0_to_l1 = (rxcui1 in layer0_rxcuis and rxcui2 in layer1_rxcuis)
                is_l1_to_l0 = (rxcui1 in layer1_rxcuis and rxcui2 in layer0_rxcuis)

                if is_l0_to_l1 or is_l1_to_l0:
                    relationship_counts[rela] += 1
                    relationships.append({
                        'rxcui_from': rxcui1,
                        'rxcui_to': rxcui2,
                        'relationship_type': rela
                    })

    print(f"✅ Found {len(relationships)} explicit relationships.")

    # --- OUTPUT RESULTS ---
    
    # 1. Print distribution of Layer 1 TTYs
    print("\n--- Distribution of Layer 1 Node Types (TTY) ---")
    tty_counts = defaultdict(int)
    for node in layer1_nodes.values():
        tty_counts[node['tty']] += 1
    for tty, count in sorted(tty_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"TTY '{tty}': {count} nodes")

    # 2. Print distribution of relationship types
    print("\n--- Distribution of Relationship Types ---")
    for rela, count in sorted(relationship_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"Relationship '{rela}': {count} instances")

    # 3. Save Layer 1 Nodes to CSV
    layer1_df = pd.DataFrame.from_dict(layer1_nodes, orient='index').reset_index()
    layer1_df.rename(columns={'index': 'rxcui'}, inplace=True)
    layer1_df.to_csv(LAYER1_NODES_PATH, index=False)
    print(f"\n✅ Saved Layer 1 nodes to {LAYER1_NODES_PATH}")

    # 4. Save Relationships to CSV
    rel_df = pd.DataFrame(relationships)
    rel_df.to_csv(RELATIONSHIPS_PATH, index=False)
    print(f"✅ Saved relationships to {RELATIONSHIPS_PATH}")

    print("\n--- Process Complete ---")

if __name__ == "__main__":
    build_layer1_and_relationships()
