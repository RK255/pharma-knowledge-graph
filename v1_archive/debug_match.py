import pandas as pd
from collections import defaultdict

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

def debug_match():
    print("--- Debugging Name Matching ---")

    # 1. Load our Layer 0 ingredients and their names
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    ingredient_map = dict(zip(ingredients_df['rxcui'].astype(str), ingredients_df['ingredient_name']))
    
    # Get the first 5 ingredients to test
    sample_ingredients = list(ingredient_map.items())[:5]
    print(f"✅ Loaded {len(ingredient_map)} ingredients. Testing first 5.")

    # 2. Build a map of all normalized names to their RxCui and TTY
    print(f"Building name-to-RxCui map from {RXNCONSO_PATH}...")
    name_to_details = defaultdict(list) # Map name to list of (rxcui, tty)
    
    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                rxcui, name, tty, sab = parts[0], parts[14], parts[12], parts[11]
                if sab == 'RXNORM':
                    normalized_name = name.lower()
                    name_to_details[normalized_name].append({'rxcui': rxcui, 'tty': tty})

    print(f"✅ Built map for {len(name_to_details)} unique normalized names.")

    # 3. Compare the sample ingredients against the map
    print("\n--- Matching Test ---")
    for rxcui, name in sample_ingredients:
        normalized_name = name.lower()
        print(f"\nTesting Ingredient: RxCUI='{rxcui}', Name='{name}'")
        print(f"  Normalized Name: '{normalized_name}'")
        
        if normalized_name in name_to_details:
            print(f"  ✅ MATCH FOUND! Connected concepts:")
            for detail in name_to_details[normalized_name]:
                print(f"    - RxCUI: {detail['rxcui']}, TTY: {detail['tty']}")
        else:
            print(f"  ❌ NO MATCH FOUND.")
            # Let's find some similar names to see what's going on
            print("  Searching for similar names (containing the first word)...")
            first_word = normalized_name.split()[0]
            found_similar = False
            for map_name, details in name_to_details.items():
                if first_word in map_name and map_name != normalized_name:
                    if not found_similar:
                        found_similar = True
                        print("    Similar names found:")
                    print(f"    - '{map_name}' (e.g., RxCUI: {details[0]['rxcui']}, TTY: {details[0]['tty']})")
            if not found_similar:
                print("    No similar names found.")

if __name__ == "__main__":
    debug_match()
