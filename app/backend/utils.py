import os
import yaml
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
            "styles": {"name": {"fontsize": 16, "spaceAfter": 12, "fontName": "Helvetica-Bold", "alignment": "center"}},
            "spaces": {"horizontal": {"education1": 105}}
        }

def merge_variables(default_vars: Dict, user_vars: Dict) -> Dict:
    """Recursively merges user-provided variables into the defaults."""
    if user_vars is None:
        return default_vars
    # Create a deep copy to avoid modifying the original default_vars
    merged = default_vars.copy()
    for key, value in user_vars.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_variables(merged[key], value)
        else:
            merged[key] = value
    return merged
