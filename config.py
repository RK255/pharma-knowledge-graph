import os
from pathlib import Path

# Base directory for all data (graph_workshop root by default).
# The pipeline repo lives at <BASE_DIR>/scripts/production/pipeline, so BASE_DIR
# is 4 parents up from this file. Override with GRC20_BASE_DIR for custom installs.
BASE_DIR = Path(os.getenv('GRC20_BASE_DIR', Path(__file__).resolve().parents[3]))

# Pipeline-specific paths
PIPELINE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DAILYMED_DIR = DATA_DIR / 'dailymed'
RAW_DATA_DIR = DATA_DIR / 'raw_data'
GRC20_OUTPUT_DIR = DATA_DIR / 'grc20_v2'
PRICING_DIR = BASE_DIR / 'scripts' / 'production' / 'pricing'

def get_path(env_var, default):
    return Path(os.getenv(env_var, str(default)))
