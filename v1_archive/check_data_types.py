import pandas as pd

# --- Configuration ---
LAYER0_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/RxNorm2026-02-10_merged_by_Date_IUPAC_SMILES.csv"
LAYER1_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_ROSETTA_2026-02-10.csv"

def check_data_types():
    print("--- Checking Data Types of RxCUIs in CSVs ---")

    # 1. Load Layer 0
    print(f"Loading {LAYER0_CSV_PATH}...")
    layer0_df = pd.read_csv(LAYER0_CSV_PATH)
    layer0_rxcuis = set(layer0_df['rxcui'])
    print(f"✅ Loaded {len(layer0_rxcuis)} RxCUIs.")
    
    # 2. Load Layer 1
    print(f"Loading {LAYER1_NODES_PATH}...")
    layer1_df = pd.read_csv(LAYER1_NODES_PATH)
    layer1_rxcuis = set(layer1_df['rxcui'])
    print(f"✅ Loaded {len(layer1_rxcuis)} RxCUIs.")

    # 3. Check data types
    print("\n--- Data Type Check ---")
    l0_sample = list(layer0_rxcuis)[:5]
    l1_sample = list(layer1_rxcuis)[:5]
    
    print(f"Layer 0 RxCUIs are of type: {type(l0_sample[0])}")
    print(f"  Sample: {l0_sample}")
    
    print(f"Layer 1 RxCUIs are of type: {type(l1_sample[0])}")
    print(f"  Sample: {l1_sample}")

    # 4. Test a set membership with a string
    print("\n--- Set Membership Test ---")
    test_string = str(l0_sample[0])
    print(f"Is string version of Layer 0 RxCui '{test_string}' in Layer 0 set? {'Yes' if test_string in layer0_rxcuis else 'No'}")
    print(f"Is string version of Layer 0 RxCui '{test_string}' in Layer 1 set? {'Yes' if test_string in layer1_rxcuis else 'No'}")


if __name__ == "__main__":
    check_data_types()
