import os
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Import modularized functions and classes
from utils import get_app_id, APPLICATIONS_DIR, BASE_RESUME_PATH
from llm_services import agent_resume_tailor
from pdf_services import ATSResumePDFGenerator

# --- Load Environment Variables ---
load_dotenv()

# --- App Initialization ---
app = FastAPI(
    title="ApplySmart Backend",
    description="Manages job applications, generates ATS-optimized assets, and renders PDFs.",
    version="6.0.0" # Version bump for refactoring
)

# --- CORS Middleware ---
origins = [
    "http://localhost:8080",
    "http://localhost",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class ApplicationData(BaseModel):
    companyName: str
    roleTitle: str

class JobDescriptionData(BaseModel):
    htmlContent: str

# --- API Endpoints ---
@app.on_event("startup")
def on_startup():
    """Create applications directory on startup if it doesn't exist."""
    if not os.path.exists(APPLICATIONS_DIR):
        os.makedirs(APPLICATIONS_DIR)
    if not os.path.exists(BASE_RESUME_PATH):
        raise FileNotFoundError(f"Base resume not found at '{BASE_RESUME_PATH}'")

@app.get("/applications", response_model=List[Dict[str, str]])
def get_applications():
    """Lists all existing applications."""
    apps = []
    if not os.path.exists(APPLICATIONS_DIR):
        return []
    for app_id in os.listdir(APPLICATIONS_DIR):
        if os.path.isdir(os.path.join(APPLICATIONS_DIR, app_id)):
            try:
                company_part, role_part = app_id.rsplit('_', 1)
                apps.append({"appId": app_id, "company": company_part.replace('_', ' '), "role": role_part.replace('_', ' ')})
            except ValueError:
                continue
    return apps

@app.get("/applications/{app_id}", response_model=Dict[str, Any])
def get_application_details(app_id: str):
    """Retrieves details for a specific application."""
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")

    jd_path = os.path.join(app_path, "job_description.html")
    yaml_path = os.path.join(app_path, "tailored_resume.yaml")

    jd_content = ""
    if os.path.exists(jd_path):
        with open(jd_path, 'r', encoding='utf-8') as f:
            jd_content = f.read()

    yaml_content = ""
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()

    return {"jobDescription": jd_content, "resumeYaml": yaml_content}

@app.post("/applications", response_model=Dict[str, str])
def create_application(data: ApplicationData):
    """Creates a new application directory."""
    app_id = get_app_id(data.companyName, data.roleTitle)
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if os.path.exists(app_path):
        raise HTTPException(status_code=409, detail="Application already exists.")
    os.makedirs(app_path)
    return {"message": "Application created successfully", "appId": app_id}

@app.post("/applications/{app_id}/job-description", response_model=Dict[str, str])
def save_job_description(app_id: str, data: JobDescriptionData):
    """Saves the job description HTML."""
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.exists(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
    file_path = os.path.join(app_path, "job_description.html")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(data.htmlContent)
    return {"message": "Job Description saved successfully."}

@app.post("/applications/{app_id}/generate-resume", response_model=Dict[str, Any])
def generate_resume(app_id: str):
    """Generates a tailored resume YAML using the LLM."""
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    jd_path = os.path.join(app_path, "job_description.html")
    if not os.path.exists(jd_path):
        raise HTTPException(status_code=404, detail="Job description not found.")

    with open(BASE_RESUME_PATH, 'r', encoding='utf-8') as f:
        base_resume_yaml = f.read()
    with open(jd_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        jd_text = soup.get_text(separator='\n', strip=True)

    tailored_yaml = agent_resume_tailor(jd_text, base_resume_yaml)

    yaml_path = os.path.join(app_path, "tailored_resume.yaml")
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(tailored_yaml)

    return {"message": "Tailored resume YAML generated successfully", "resumeYaml": tailored_yaml}

@app.post("/applications/{app_id}/render-pdf")
def render_pdf(app_id: str):
    """Renders the tailored resume YAML into a PDF."""
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    yaml_path = os.path.join(app_path, "tailored_resume.yaml")

    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="YAML resume not found. Please generate it first.")

    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    pdf_path = os.path.join(app_path, "tailored_resume.pdf")
    pdf_generator = ATSResumePDFGenerator()
    pdf_generator.generate_pdf_from_data(data, pdf_path)
    
    return FileResponse(pdf_path, media_type='application/pdf', filename=f"{app_id}_resume.pdf")
