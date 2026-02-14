import pandas as pd
from collections import defaultdict

# --- Configuration ---
# Path to your clean, enriched ingredient list
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"

# Path to the raw RxNorm relationship file
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"

# Path for the output file
OUTPUT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Connected_RxCUIs_2026-02-10.csv"

def find_connected_nodes():
    """
    Finds all RxCUIs connected to our list of ingredients using the RXNREL.RRF file.
    """
    print("--- Starting Connected Node Analysis ---")

    # 1. Load our list of ingredient RxCUIs
    print(f"Loading ingredient list from {INGREDIENT_CSV_PATH}...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    ingredient_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(ingredient_rxcuis)} unique ingredient RxCUIs.")

    # 2. Initialize a set to store all connected RxCUIs
    connected_rxcuis = set()
    relationship_counts = defaultdict(int)

    # 3. Process the RXNREL.RRF file
    print(f"Processing {RXNREL_PATH} to find connections...")
    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 8:
                rxcui1 = parts[4]
                rxcui2 = parts[7]
                rel_type = parts[6] # e.g., 'has_ingredient', 'isa', etc.

                # Check if either side of the relationship is one of our ingredients
                if rxcui1 in ingredient_rxcuis:
                    connected_rxcuis.add(rxcui2)
                    relationship_counts[rel_type] += 1
                elif rxcui2 in ingredient_rxcuis:
                    connected_rxcuis.add(rxcui1)
                    relationship_counts[rel_type] += 1

    print(f"✅ Found {len(connected_rxcuis)} unique RxCUIs connected to our ingredients.")
    
    # 4. Print the distribution of relationship types
    print("\n--- Distribution of Relationship Types ---")
    for rel_type, count in sorted(relationship_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"{rel_type}: {count}")

    # 5. Save the list of connected RxCUIs
    connected_df = pd.DataFrame(list(connected_rxcuis), columns=['connected_rxcui'])
    connected_df.to_csv(OUTPUT_CSV_PATH, index=False)
    print(f"\n✅ Saved list of connected RxCUIs to {OUTPUT_CSV_PATH}")

    print("--- Analysis Complete ---")

if __name__ == "__main__":
    find_connected_nodes()
