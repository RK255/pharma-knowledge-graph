import pandas as pd

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"

def debug_final_columns():
    print("--- Final Column Index Debug ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Scan RXNREL and find the first line with a known ingredient
    print(f"\nScanning {RXNREL_PATH} for a relationship with RxCUI '1760' (mesna)...")
    
    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            
            # Let's just search the whole line for our target RxCUI
            if '1760' in line:
                print(f"\n--- FOUND A MATCHING LINE ---")
                print(f"Raw Line: {line.strip()}")
                print(f"\n--- Parsed Parts with Indices ---")
                for i, part in enumerate(parts):
                    print(f"Index {i}: '{part}'")
                
                print("\n--- Our Current Logic ---")
                print(f"rxcui1 = parts[4]  -> '{parts[4]}'")
                print(f"rela   = parts[7]  -> '{parts[7]}'")
                print(f"rxcui2 = parts[5]  -> '{parts[5]}'")

                print("\n--- Alternative Logic (Based on Docs) ---")
                print(f"rxcui1 = parts[0]  -> '{parts[0]}'") # Based on some examples online
                print(f"rela   = parts[3]  -> '{parts[3]}'") # Based on some examples online
                print(f"rxcui2 = parts[4]  -> '{parts[4]}'") # Based on docs

                break # Stop after the first match

if __name__ == "__main__":
    debug_final_columns()
