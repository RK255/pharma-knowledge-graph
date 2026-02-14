import pandas as pd
from collections import defaultdict

# --- Configuration ---
# Path to your clean, enriched ingredient list
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"

# Path to the raw RxNorm files
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

def analyze_connections_by_tty():
    """
    Finds all nodes connected to our INs and categorizes them by TTY.
    """
    print("--- Starting Analysis of Connections by TTY ---")

    # 1. Load our list of ingredient RxCUIs
    print(f"Loading ingredient list from {INGREDIENT_CSV_PATH}...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    ingredient_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(ingredient_rxcuis)} unique ingredient RxCUIs (TTY=IN).")

    # 2. Find all connected RxCUIs from RXNREL
    print(f"Processing {RXNREL_PATH} to find all connected nodes...")
    connected_rxcuis = set()

    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 8:
                rxcui1, rxcui2 = parts[4], parts[7]

                # If our ingredient is on one side, add the other side to the set
                if rxcui1 in ingredient_rxcuis:
                    connected_rxcuis.add(rxcui2)
                elif rxcui2 in ingredient_rxcuis:
                    connected_rxcuis.add(rxcui1)

    # Remove our original ingredients from the connected list
    connected_rxcuis.difference_update(ingredient_rxcuis)
    print(f"✅ Found {len(connected_rxcuis)} unique RxCUIs connected to our ingredients.")

    # 3. Look up TTY for each connected RxCUI in RXNCONSO.RRF
    print(f"\nProcessing {RXNCONSO_PATH} to find TTY codes for connected nodes...")
    rxcui_to_tty = {}
    tty_counts = defaultdict(int)

    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                rxcui, tty, suppress = parts[0], parts[12], parts[17]
                
                # If this is a connected RxCUI we haven't seen yet, and it's active
                if rxcui in connected_rxcuis and rxcui not in rxcui_to_tty and suppress == 'N':
                    rxcui_to_tty[rxcui] = tty
                    tty_counts[tty] += 1

    print(f"✅ Found TTY codes for {len(rxcui_to_tty)} connected RxCUIs.")

    # 4. Print the distribution of TTY codes - THIS IS THE KEY OUTPUT
    print("\n--- Distribution of Connected Node Types (TTY) ---")
    print("This shows what all the 'things' connected to your ingredients are:")
    for tty, count in sorted(tty_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"TTY '{tty}': {count} nodes")

    # Optional: Save the results if you want to inspect them
    # results_df = pd.DataFrame(list(rxcui_to_tty.items()), columns=['connected_rxcui', 'tty'])
    # results_df.to_csv('/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Connected_RxCUIs_with_TTY.csv', index=False)
    # print(f"\n✅ Saved connected RxCUIs and their TTY codes to Connected_RxCUIs_with_TTY.csv")

    print("\n--- Analysis Complete ---")

if __name__ == "__main__":
    analyze_connections_by_tty()
