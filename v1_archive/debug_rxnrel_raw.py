import pandas as pd

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"

def debug_rxnrel_raw():
    print("--- Debugging RXNREL.RRF with Raw Output ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Scan RXNREL and print the first few matching lines
    print(f"\nScanning {RXNREL_PATH} and printing first 5 matching lines...")
    found_count = 0
    
    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            # RXNREL has at least 9 columns
            if len(parts) >= 9:
                rxcui1 = parts[4]
                rela = parts[7] # NOTE: Rela is in column 8, not 7
                rxcui2 = parts[8] # NOTE: Rxcui2 is in column 9, not 8

                if rxcui1 in layer0_rxcuis or rxcui2 in layer0_rxcuis:
                    found_count += 1
                    print(f"\n--- Match #{found_count} ---")
                    print(f"Raw Line: {line.strip()}")
                    print(f"Parsed Parts: {parts}")
                    print(f"rxcui1='{rxcui1}', rela='{rela}', rxcui2='{rxcui2}'")
                    
                    if found_count >= 5:
                        break

if __name__ == "__main__":
    debug_rxnrel_raw()
