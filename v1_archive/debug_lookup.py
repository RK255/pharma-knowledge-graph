import pandas as pd

# --- Configuration ---
# We'll read the Layer 1 list directly from the CSV your script just created
LAYER1_CSV_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer1_Nodes_Grab_Subtract_2026-02-10.csv"
RXNCONSO_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/raw_data/extracted_rrf/RXNCONSO.RRF"

def debug_lookup():
    print("--- Debugging RXNCONSO.RRF Lookup ---")

    # 1. Load the list of Layer 1 RxCUIs we just found
    print(f"Loading Layer 1 RxCUIs from {LAYER1_CSV_PATH}...")
    try:
        layer1_df = pd.read_csv(LAYER1_CSV_PATH)
        layer1_rxcuis = set(layer1_df['rxcui'].astype(str))
        print(f"✅ Loaded {len(layer1_rxcuis)} Layer 1 RxCUIs from the CSV.")
    except FileNotFoundError:
        print("❌ ERROR: Could not find the Layer 1 CSV file. Did the previous script run correctly?")
        return

    # 2. Scan RXNCONSO and look for the first few Layer 1 RxCUIs
    print(f"\nScanning {RXNCONSO_PATH} for the first 5 Layer 1 RxCUIs...")
    sample_rxcuis = list(layer1_rxcuis)[:5]
    found_count = 0
    conso_rxcuis = set()

    with open(RXNCONSO_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 18:
                rxcui = parts[0]
                conso_rxcuis.add(rxcui)
                
                if rxcui in sample_rxcuis:
                    found_count += 1
                    print(f"\n--- Match for RxCUI '{rxcui}' ---")
                    print(f"Raw Line: {line.strip()}")
                    print(f"Name: '{parts[14]}'")
                    print(f"TTY: '{parts[12]}'")
                    print(f"SAB: '{parts[11]}'")
                    
                    if found_count >= len(sample_rxcuis):
                        break
    
    print(f"\n--- Summary ---")
    print(f"Found {found_count} of the {len(sample_rxcuis)} sample RxCUIs in RXNCONSO.RRF.")
    print(f"Total unique RxCUIs found in RXNCONSO.RRF: {len(conso_rxcuis)}")

    # Check for data type mismatches
    print("\n--- Checking for Data Type Mismatches ---")
    sample_from_rel = list(layer1_rxcuis)[0]
    sample_from_conso = list(conso_rxcuis)[0]
    print(f"Example Layer 1 RxCUI type: '{type(sample_from_rel)}', value: '{sample_from_rel}'")
    print(f"Example RXNCONSO RxCUI type: '{type(sample_from_conso)}', value: '{sample_from_conso}'")


if __name__ == "__main__":
    debug_lookup()
