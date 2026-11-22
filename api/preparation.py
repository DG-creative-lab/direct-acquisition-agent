"""Vercel Python function entry point."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from acquisition.entrypoints.serverless_preparation import handler as PreparationHandler


class handler(PreparationHandler):
    pass
