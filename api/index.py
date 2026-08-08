"""Vercel serverless entry point for FinOps Intelligence FastAPI application."""

import sys
from pathlib import Path

# Ensure project root is in Python path for Vercel serverless environment
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.main import app
