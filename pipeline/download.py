#!/usr/bin/env python3
"""Download a country's source files: python pipeline/download.py <cc> <raw_dir>"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import countries  # noqa: E402

cc, raw_dir = sys.argv[1], sys.argv[2]
os.makedirs(raw_dir, exist_ok=True)
countries.get(cc).download(raw_dir)
