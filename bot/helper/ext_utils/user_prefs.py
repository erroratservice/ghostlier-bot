import json
import os

PREFS_FILE = "user_prefs.json"

def _load_prefs():
    if not os.path.exists(PREFS_FILE):
        return {}
    with open(PREFS_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def _save_prefs(prefs):
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)

def set_user_pref(user_id, key, value):
    prefs = _load_prefs()
    user_id = str(user_id)
    if user_id not in prefs:
        prefs[user_id] = {}
    prefs[user_id][key] = value
    _save_prefs(prefs)

def get_user_pref(user_id, key, default=None):
    prefs = _load_prefs()
    return prefs.get(str(user_id), {}).get(key, default)
