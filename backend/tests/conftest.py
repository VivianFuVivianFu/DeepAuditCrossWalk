"""Isolate test defaults from operator environment variables."""

import os

os.environ["ENV"] = "test"
os.environ.pop("CROSSWALK_API_KEY", None)
os.environ.pop("DATABASE_URL", None)
