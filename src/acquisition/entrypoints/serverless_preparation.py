"""Private operator function entry point; all concrete composition lives in bootstrap."""
from acquisition.bootstrap import build_serverless_preparation_handler

handler = build_serverless_preparation_handler()
