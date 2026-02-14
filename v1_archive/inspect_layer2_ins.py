import pandas as pd

# --- Configuration ---
# Use the output from the last run
LAYER2_NODES_PATH = "/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer2_Nodes_FILTERED_FINAL_2026-02-10.csv"

def inspect_layer2_ins():
    print("--- Inspecting 'IN' nodes found in Layer 2 ---")

    # 1. Load the Layer 2 nodes
    print(f"Loading Layer 2 nodes from {LAYER2_NODES_PATH}...")
    try:
        layer2_df = pd.read_csv(LAYER2_NODES_PATH)
    except FileNotFoundError:
        print("❌ ERROR: Could not find the Layer 2 nodes CSV file.")
        return

    # 2. Filter for only the 'IN' TTY nodes
    in_nodes_df = layer2_df[layer2_df['tty'] == 'IN']
    
    print(f"✅ Found {len(in_nodes_df)} nodes with TTY='IN' in Layer 2.")

    if len(in_nodes_df) == 0:
        print("No IN nodes found. The script may have worked correctly after all.")
        return

    # 3. Print the details for these nodes
    print("\n--- Details for 'IN' Nodes in Layer 2 ---")
    print(in_nodes_df.to_string())

    # 4. (Optional) Save just this list to a separate file for easier inspection
    in_nodes_df.to_csv("/mnt/fast_raid/server_projects/Geo/graph_workshop/data/import_csvs/Layer2_INs_only_2026-02-10.csv", index=False)
    print(f"\n✅ Saved the list of 'IN' nodes to Layer2_INs_only_2026-02-10.csv")

if __name__ == "__main__":
    inspect_layer2_ins()
