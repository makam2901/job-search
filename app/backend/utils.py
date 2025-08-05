import os
import yaml
import copy
from typing import Dict

# --- Constants ---
APPLICATIONS_DIR = "/app/applications"
BASE_RESUME_PATH = "/app/manikesh_resume_ats.yaml"
VARIABLES_PATH = "/app/variables.yaml"

# --- Helper Functions ---
def get_app_id(company_name: str, role_title: str) -> str:
    """Creates a safe directory name from company and role titles."""
    safe_company = "".join(c if c.isalnum() else '_' for c in company_name)
    safe_role = "".join(c if c.isalnum() else '_' for c in role_title)
    # Reverted to a simpler separator logic
    return f"{safe_company}_{safe_role}"

def load_variables() -> Dict:
    """Loads formatting variables from the YAML file."""
    try:
        with open(VARIABLES_PATH, 'r') as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError):
        # Provide a fallback default if the file is missing or corrupt
        print("Warning: variables.yaml not found or is invalid. Using fallback defaults.")
        return {
            "general": {"show_summary": True},
            "styles": {"name": {"fontsize": 16, "spaceAfter": 12, "fontName": "Helvetica-Bold", "alignment": "center"}},
            "spaces": {"horizontal": {"education1": 105}}
        }

def merge_variables(base: Dict, updates: Dict) -> Dict:
    """
    Recursively merges the 'updates' dictionary into a deep copy of the 'base' dictionary.
    This ensures that the base dictionary is not modified and there are no side effects.
    """
    # Start with a deep copy of the base to avoid any mutation of the original object.
    merged = copy.deepcopy(base)
    
    if updates is None:
        return merged

    for key, value in updates.items():
        # If the key exists in both dictionaries and both values are dictionaries, recurse.
        if isinstance(value, dict) and key in merged and isinstance(merged.get(key), dict):
            merged[key] = merge_variables(merged[key], value)
        else:
            # Otherwise, the value from the updates dictionary overwrites the base.
            merged[key] = value
            
    return merged
