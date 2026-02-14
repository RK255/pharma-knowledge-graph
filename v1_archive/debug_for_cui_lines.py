import pandas as pd

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"

def debug_for_cui_lines():
    print("--- Debugging RXNREL.RRF for CUI Lines Only ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Scan RXNREL and find the first line with a known ingredient AND 'CUI' as the source
    print(f"\nScanning {RXNREL_PATH} for a 'CUI' relationship with RxCUI '1760' (mesna)...")
    
    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            
            # Check if this line involves our target RxCUI and has 'CUI' as the source type
            # Based on our last debug, source type is at index 2
            if '1760' in line and len(parts) > 2 and parts[2] == 'CUI':
                print(f"\n--- FOUND A 'CUI' MATCHING LINE ---")
                print(f"Raw Line: {line.strip()}")
                print(f"\n--- Parsed Parts with Indices ---")
                for i, part in enumerate(parts):
                    print(f"Index {i}: '{part}'")
                
                print("\n--- Interpreting this CUI Line ---")
                # Let's assume the first non-empty field is RXCUI1
                rxcui1 = ''
                for i, part in enumerate(parts):
                    if part:
                        rxcui1 = part
                        break
                print(f"Likely RXCUI1: '{rxcui1}'")
                print(f"Source Type (STYPE1): '{parts[2]}' -> '{parts[3]}'")
                print(f"Relationship (REL): '{parts[3]}' -> '{parts[4]}'")
                print(f"Likely RXCUI2: '{parts[5]}'") # This is a guess, let's see

                break # Stop after the first match

if __name__ == "__main__":
    debug_for_cui_lines()
