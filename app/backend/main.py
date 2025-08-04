import os
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Import modularized functions and classes
from utils import get_app_id, APPLICATIONS_DIR, BASE_RESUME_PATH, load_variables, merge_variables
from llm_services import agent_resume_tailor
from pdf_services import ATSResumePDFGenerator

# --- Load Environment Variables ---
load_dotenv()

# --- App Initialization ---
app = FastAPI(
    title="ApplySmart Backend",
    description="Manages job applications and renders PDFs with dynamic formatting.",
    version="8.1.0" # Version bump for rendering logic update
)

# --- CORS Middleware ---
origins = ["http://localhost:8080", "http://localhost"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Pydantic Models ---
class ApplicationData(BaseModel):
    companyName: str
    roleTitle: str

class JobDescriptionData(BaseModel):
    htmlContent: str

class RenderRequestData(BaseModel):
    resumeYaml: str
    variables: Optional[Dict[str, Any]] = Field(None, description="Optional override for formatting variables")

class SaveVariablesRequest(BaseModel):
    variables: Dict[str, Any]

# --- API Endpoints ---
@app.on_event("startup")
def on_startup():
    if not os.path.exists(APPLICATIONS_DIR): os.makedirs(APPLICATIONS_DIR)
    if not os.path.exists(BASE_RESUME_PATH): raise FileNotFoundError(f"Base resume not found at '{BASE_RESUME_PATH}'")

@app.get("/default-variables", response_model=Dict)
def get_default_variables():
    return load_variables()

@app.get("/applications", response_model=List[Dict[str, str]])
def get_applications():
    apps = []
    if not os.path.exists(APPLICATIONS_DIR): return []
    for app_id in os.listdir(APPLICATIONS_DIR):
        if os.path.isdir(os.path.join(APPLICATIONS_DIR, app_id)):
            try:
                company_part, role_part = app_id.rsplit('_', 1)
                apps.append({"appId": app_id, "company": company_part.replace('_', ' '), "role": role_part.replace('_', ' ')})
            except ValueError: continue
    return apps

@app.get("/applications/{app_id}", response_model=Dict[str, Any])
def get_application_details(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path): raise HTTPException(status_code=404, detail="Application not found.")
    
    jd_path = os.path.join(app_path, "job_description.html")
    yaml_path = os.path.join(app_path, "tailored_resume.yaml")
    custom_vars_path = os.path.join(app_path, "custom_variables.yaml")

    jd_content = ""
    if os.path.exists(jd_path):
        with open(jd_path, 'r', encoding='utf-8') as f: jd_content = f.read()
    
    yaml_content = ""
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f: yaml_content = f.read()

    custom_vars = None
    if os.path.exists(custom_vars_path):
        with open(custom_vars_path, 'r', encoding='utf-8') as f:
            custom_vars = yaml.safe_load(f)

    return {"jobDescription": jd_content, "resumeYaml": yaml_content, "customVariables": custom_vars}

@app.post("/applications", response_model=Dict[str, str])
def create_application(data: ApplicationData):
    app_id = get_app_id(data.companyName, data.roleTitle)
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if os.path.exists(app_path): raise HTTPException(status_code=409, detail="Application already exists.")
    os.makedirs(app_path)
    return {"message": "Application created successfully", "appId": app_id}

@app.post("/applications/{app_id}/job-description", response_model=Dict[str, str])
def save_job_description(app_id: str, data: JobDescriptionData):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.exists(app_path): raise HTTPException(status_code=404, detail="Application not found.")
    file_path = os.path.join(app_path, "job_description.html")
    with open(file_path, 'w', encoding='utf-8') as f: f.write(data.htmlContent)
    return {"message": "Job Description saved successfully."}

@app.post("/applications/{app_id}/generate-resume", response_model=Dict[str, Any])
def generate_resume(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    jd_path = os.path.join(app_path, "job_description.html")
    if not os.path.exists(jd_path): raise HTTPException(status_code=404, detail="Job description not found.")
    with open(BASE_RESUME_PATH, 'r', encoding='utf-8') as f: base_resume_yaml = f.read()
    with open(jd_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        jd_text = soup.get_text(separator='\n', strip=True)
    tailored_yaml = agent_resume_tailor(jd_text, base_resume_yaml)
    yaml_path = os.path.join(app_path, "tailored_resume.yaml")
    with open(yaml_path, 'w', encoding='utf-8') as f: f.write(tailored_yaml)
    return {"message": "Tailored resume YAML generated successfully", "resumeYaml": tailored_yaml}

@app.post("/applications/{app_id}/save-variables", response_model=Dict[str, str])
def save_variables(app_id: str, request: SaveVariablesRequest):
    """Saves the user's custom formatting variables for a specific application."""
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
    
    vars_path = os.path.join(app_path, "custom_variables.yaml")
    try:
        with open(vars_path, 'w', encoding='utf-8') as f:
            yaml.dump(request.variables, f, allow_unicode=True, sort_keys=False)
        return {"message": "Configuration saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {e}")

@app.post("/applications/{app_id}/render-pdf")
def render_pdf(app_id: str, data: RenderRequestData):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
        
    try:
        resume_data = yaml.safe_load(data.resumeYaml)
    except yaml.YAMLError:
        raise HTTPException(status_code=400, detail="Invalid YAML format in resume data.")

    # Load global defaults
    final_vars = load_variables()
    
    # Load and merge application-specific saved variables
    custom_vars_path = os.path.join(app_path, "custom_variables.yaml")
    if os.path.exists(custom_vars_path):
        with open(custom_vars_path, 'r', encoding='utf-8') as f:
            app_specific_vars = yaml.safe_load(f)
            final_vars = merge_variables(final_vars, app_specific_vars)

    # Merge live variables from the request on top of everything
    final_vars = merge_variables(final_vars, data.variables)

    pdf_path = os.path.join(app_path, "tailored_resume.pdf")
    pdf_generator = ATSResumePDFGenerator(variables=final_vars)
    pdf_generator.generate_pdf_from_data(resume_data, pdf_path)
    
    return FileResponse(pdf_path, media_type='application/pdf', filename=f"{app_id}_resume.pdf")
