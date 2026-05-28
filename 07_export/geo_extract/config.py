# config.py
from pathlib import Path

BASE_DIR     = Path("/mnt/fast_raid/server_projects/Geo/graph_workshop")
DATA_DIR     = BASE_DIR / "data" / "grc20_v2"
RAW_DATA_DIR = BASE_DIR / "data" / "raw_data"
OUTPUT_DIR   = BASE_DIR / "scripts" / "production" / "geo-ingestor" / "data_to_publish"

RXNORM_ENTITIES_FILE  = DATA_DIR     / "rxnorm_entities_enriched.jsonl"
RXNORM_RELATIONS_FILE = DATA_DIR     / "rxnorm_relations.jsonl"
CID_MAPPING_FILE      = DATA_DIR     / "pubchem_cid_mapping.json"
NDC_MERGED_FILE       = RAW_DATA_DIR / "ndc_merged.json"
NDC_TO_SETID_FILE     = RAW_DATA_DIR / "ndc_to_setid.json"
PRICING_FILE          = BASE_DIR / "data" / "pricing" / "analysis" / "pricing_for_your_ndcs.json"
OUTPUT_FILE           = OUTPUT_DIR / "full_geo_extraction_v23.jsonl"

# ── Property IDs ──────────────────────────────────────────────────────────────
PROP_NAME      = 'a126ca530c8e48d5b88882c734c38935'
PROP_RXCUI     = 'c6f36f8a8e22546ea7618ac008d2f91e'
PROP_TTY       = 'fd0c76eae47c55bbac4cca96203752c1'
PROP_CID       = 'bdd863e095365bbea65deae8ebf1e81b'
PROP_SMILES    = '56e99a1b93b2573689e2f6a6c662df10'
PROP_INCHIKEY  = '6b432fc791ad5358b1f17fdc6abcfacc'
PROP_IUPAC     = '5fbf742a110d508abc9af6a1cd1e49e7'
PROP_MOLWEIGHT = '20aba01a611d57e1bb02ca665dd61acd'
PROP_PMID      = 'c2842d1831e35b2f82fb74b532f4508b'

# ── Relation IDs ──────────────────────────────────────────────────────────────
REL_HAS_INGREDIENT         = 'd085f236da3c51fca583c72e7058973b'
REL_INGREDIENT_OF          = '708910ff645b507ab5616dbd680b5802'
REL_HAS_PRECISE_INGREDIENT = '307907247a3c5be682ed242bb61a2947'
REL_PRECISE_INGREDIENT_OF  = '9147c85a51ea5a2481824d2aefe5956d'
REL_HAS_INGREDIENTS        = '73f2d9bc321054dc80888064f36282fb'
REL_INGREDIENTS_OF         = 'f44019f93b2258119d1022c4f39b9da5'
REL_HAS_PART               = '94272e15b3535feab43867d3b374f608'
REL_PART_OF                = '1df119c2ba785c688aafd35556f3fab6'
REL_CONSISTS_OF            = '88c43b5be4eb5fe78b09872e9a9c3c70'
REL_CONSTITUTES            = 'f5e289c3d13a5aaaa38b22448f7e38ab'
REL_HAS_TRADENAME          = 'a42836a8c04757e1a995531b8ff3200b'
REL_TRADENAME_OF           = 'dbc766b554f0579da4c7b7c29924d6a3'
REL_HAS_DOSE_FORM          = '29f07e00f9d45f76aef7e6c03f00441b'
REL_DOSE_FORM_OF           = 'cbf90e604bf458719df7ad10fd90c07f'

BLOCKED_TTYS          = {'TMSY', 'PSN', 'SY'}
INJECTABLE_DOSE_FORMS = ['Auto-Injector', 'Prefilled Syringe']
DEVICE_NAME_MAP       = {'SENSOR': 'Digihaler'}
