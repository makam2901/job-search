import os

# The working directory is set to /app in the Dockerfile
APPLICATIONS_DIR = "/app/applications"
BASE_RESUME_PATH = "/app/manikesh_resume_ats.yaml"

# --- Helper Functions ---
def get_app_id(company_name: str, role_title: str) -> str:
    """Creates a safe directory name from company and role titles."""
    safe_company = "".join(c if c.isalnum() else '_' for c in company_name)
    safe_role = "".join(c if c.isalnum() else '_' for c in role_title)
    return f"{safe_company}_{safe_role}"
