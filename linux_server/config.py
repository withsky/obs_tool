#!/usr/bin/env python3
import json
import os

def load_config(path: str, default: dict = None) -> dict:
    if default is None:
        default = {}
    if not path or not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return default
