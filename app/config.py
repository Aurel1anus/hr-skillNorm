from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "models" / "bge-small-zh-v1.5"
TOP_K = 5
SEMANTIC_THRESHOLD = 0.82
UNKNOWN_THRESHOLD = 0.70
MARGIN_THRESHOLD = 0.05
