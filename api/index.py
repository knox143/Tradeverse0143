import os
import sys
from pathlib import Path

# Add repository root to Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure VERCEL indicator is set
os.environ.setdefault("VERCEL", "1")

from app import app

# Vercel serverless function entrypoint
app = app
