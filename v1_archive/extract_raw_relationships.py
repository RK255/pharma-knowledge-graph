import pandas as pd

# --- Configuration ---
INGREDIENT_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
RXNREL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNREL.RRF"

# Path for the output file
RAW_REL_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Raw_Relationships_for_INs_2026-02-10.csv"

def extract_raw_relationships():
    """
    Pulls all raw rows from RXNREL.RRF that involve one of our IN RxCUIs.
    """
    print("--- Extracting Raw Relationships for IN RxCUIs ---")

    # 1. Load our Layer 0 ingredients
    print(f"Loading Layer 0 ingredient list...")
    ingredients_df = pd.read_csv(INGREDIENT_CSV_PATH)
    layer0_rxcuis = set(ingredients_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} unique Layer 0 ingredients.")

    # 2. Scan RXNREL and pull all matching rows
    print(f"\nScanning {RXNREL_PATH} and extracting all matching rows...")
    matching_rows = []
    
    with open(RXNREL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 9:
                rxcui1, rela, rxcui2 = parts[4], parts[7], parts[8]

                # Check if this relationship involves one of our ingredients
                if rxcui1 in layer0_rxcuis or rxcui2 in layer0_rxcuis:
                    matching_rows.append(parts)

    print(f"✅ Found {len(matching_rows)} raw relationship rows.")

    # 3. Save the raw rows to a CSV file for inspection
    # We'll create a pandas DataFrame to easily save it
    # RXNREL has 16 columns, so we'll name them for clarity
    column_names = [
        'RXCUI1', 'RXAUI1', 'STYPE1', 'REL', 'RXCUI2', 'RXAUI2', 'STYPE2', 
        'RELA', 'RUI', 'SRUI', 'SAB', 'SL', 'RG', 'DIR', 'SUPPRESS', 'CVF'
    ]
    
    # Note: Our parsing is a bit different from the official guide, so we'll align the columns
    # based on our debug output.
    # parts[4] = RXCUI1, parts[7]=RELA, parts[8]=RXCUI2
    df = pd.DataFrame(matching_rows)
    
    # Let's just save the raw parts first, then we can create a readable version
    df.to_csv(RAW_REL_PATH, index=False, header=False)
    print(f"✅ Saved raw parts to {RAW_REL_PATH}")

    # Now let's print the first 5 rows in a more readable format
    print("\n--- First 5 Matching Rows (Readable Format) ---")
    readable_columns = ['RXCUI1', 'RELA', 'RXCUI2', 'SAB', 'CVF']
    # Re-map our parsed parts to these columns
    readable_data = []
    for parts in matching_rows[:5]:
        readable_data.append([parts[4], parts[7], parts[8], parts[10], parts[15]])
    
    readable_df = pd.DataFrame(readable_data, columns=readable_columns)
    print(readable_df.to_string())


if __name__ == "__main__":
    extract_raw_relationships()
