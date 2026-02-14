import pandas as pd

# --- Configuration ---
LAYER0_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
LAYER2_INS_ONLY_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer2_INs_only_2026-02-10.csv"

def verify_in_overlap():
    print("--- Verifying Overlap Between Layer 0 and Layer 2 'IN' Codes ---")

    # 1. Load the original Layer 0 RxCUIs
    print(f"Loading Layer 0 RxCUIs...")
    layer0_df = pd.read_csv(LAYER0_CSV_PATH)
    layer0_rxcuis = set(layer0_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer0_rxcuis)} RxCUIs from Layer 0.")

    # 2. Load the Layer 2 'IN' RxCUIs
    print(f"Loading Layer 2 'IN' RxCUIs...")
    layer2_in_df = pd.read_csv(LAYER2_INS_ONLY_PATH)
    layer2_in_rxcuis = set(layer2_in_df['rxcui'].astype(str))
    print(f"✅ Loaded {len(layer2_in_rxcuis)} 'IN' RxCUIs from Layer 2.")

    # 3. Find the intersection
    print("\n--- Checking for Overlap ---")
    overlap = layer0_rxcuis.intersection(layer2_in_rxcuis)
    
    if not overlap:
        print("✅ SUCCESS: There is NO overlap between the Layer 0 and Layer 2 'IN' codes.")
        print("The filter worked correctly. These are new discoveries.")
    else:
        print(f"❌ WARNING: Found {len(overlap)} overlapping RxCUIs. The filter failed.")
        print(f"Overlapping RxCUIs: {sorted(list(overlap))}")

if __name__ == "__main__":
    verify_in_overlap()
