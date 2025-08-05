import os
import yaml
import re
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
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
    version="11.0.0" # Version bump for app creation fix
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

class FinalizeRequest(BaseModel):
    resumeYaml: str
    variables: Dict[str, Any]

# --- Helper Functions ---
def get_resume_versions(app_path: str) -> List[str]:
    """Finds all versions of the tailored resume YAML, sorted newest first."""
    if not os.path.isdir(app_path):
        return []
    
    version_pattern = re.compile(r'^tailored_resume_v(\d+)\.yaml$')
    versions = []
    for f in os.listdir(app_path):
        match = version_pattern.match(f)
        if match:
            versions.append((int(match.group(1)), f))
            
    versions.sort(key=lambda x: x[0], reverse=True)
    sorted_filenames = [filename for _, filename in versions]

    unversioned_path = os.path.join(app_path, "tailored_resume.yaml")
    if os.path.exists(unversioned_path) and "tailored_resume.yaml" not in sorted_filenames:
        sorted_filenames.append("tailored_resume.yaml")
        
    return sorted_filenames

# --- API Endpoints ---
@app.on_event("startup")
def on_startup():
    if not os.path.exists(APPLICATIONS_DIR): os.makedirs(APPLICATIONS_DIR)
    if not os.path.exists(BASE_RESUME_PATH): raise FileNotFoundError(f"Base resume not found at '{BASE_RESUME_PATH}'")

@app.get("/default-variables", response_model=Dict)
def get_default_variables():
    return load_variables()

@app.get("/applications", response_model=List[Dict[str, Any]])
def get_applications():
    apps = []
    if not os.path.exists(APPLICATIONS_DIR): return []
    
    app_dirs = [d for d in os.listdir(APPLICATIONS_DIR) if os.path.isdir(os.path.join(APPLICATIONS_DIR, d))]

    for app_id in app_dirs:
        app_path = os.path.join(APPLICATIONS_DIR, app_id)
        details_path = os.path.join(app_path, "app_details.json")
        
        if os.path.exists(details_path):
            with open(details_path, 'r') as f:
                details = json.load(f)
            
            created_at = os.path.getmtime(app_path)
            apps.append({
                "appId": app_id, 
                "company": details.get("companyName"), 
                "role": details.get("roleTitle"),
                "createdAt": created_at 
            })
        else:
            # Fallback for old applications without app_details.json
            try:
                company_part, role_part = app_id.rsplit('_', 1)
                created_at = os.path.getmtime(app_path)
                apps.append({
                    "appId": app_id, 
                    "company": company_part.replace('_', ' '), 
                    "role": role_part.replace('_', ' '),
                    "createdAt": created_at 
                })
            except ValueError:
                continue
            
    apps.sort(key=lambda x: x['createdAt'], reverse=True)
    return apps

@app.post("/applications", response_model=Dict[str, str])
def create_application(data: ApplicationData):
    app_id = get_app_id(data.companyName, data.roleTitle)
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if os.path.exists(app_path): raise HTTPException(status_code=409, detail="Application already exists.")
    os.makedirs(app_path)
    
    # Save company and role to a file
    details_path = os.path.join(app_path, "app_details.json")
    with open(details_path, 'w') as f:
        json.dump({"companyName": data.companyName, "roleTitle": data.roleTitle}, f)

    return {"message": "Application created successfully", "appId": app_id}

@app.get("/applications/{app_id}", response_model=Dict[str, Any])
def get_application_details(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path): raise HTTPException(status_code=404, detail="Application not found.")
    
    jd_path = os.path.join(app_path, "job_description.html")
    
    resume_versions = get_resume_versions(app_path)
    latest_resume_file = resume_versions[0] if resume_versions else None
    yaml_path = os.path.join(app_path, latest_resume_file) if latest_resume_file else None

    jd_content = ""
    if os.path.exists(jd_path):
        with open(jd_path, 'r', encoding='utf-8') as f: jd_content = f.read()
    
    yaml_content = ""
    if yaml_path and os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f: yaml_content = f.read()

    custom_vars_path = os.path.join(app_path, "custom_variables.yaml")
    custom_vars = None
    if os.path.exists(custom_vars_path):
        with open(custom_vars_path, 'r', encoding='utf-8') as f:
            custom_vars = yaml.safe_load(f)

    return {
        "jobDescription": jd_content, 
        "resumeYaml": yaml_content, 
        "customVariables": custom_vars, 
        "resumeVersions": resume_versions
    }

@app.get("/applications/{app_id}/resume-content")
def get_resume_version_content(app_id: str, filename: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
    
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid filename.")

    file_path = os.path.join(app_path, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume version not found.")
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    return JSONResponse(content={"resumeYaml": content})

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

    resume_versions = get_resume_versions(app_path)
    version_numbers = [int(re.search(r'_v(\d+)\.yaml$', f).group(1)) for f in resume_versions if re.search(r'_v(\d+)\.yaml$', f)]
    new_version_num = max(version_numbers) + 1 if version_numbers else 1
    new_resume_filename = f"tailored_resume_v{new_version_num}.yaml"
    yaml_path = os.path.join(app_path, new_resume_filename)

    with open(BASE_RESUME_PATH, 'r', encoding='utf-8') as f: base_resume_yaml = f.read()
    with open(jd_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        jd_text = soup.get_text(separator='\n', strip=True)
    
    tailored_yaml = agent_resume_tailor(jd_text, base_resume_yaml)
    
    with open(yaml_path, 'w', encoding='utf-8') as f: f.write(tailored_yaml)
    
    return {
        "message": f"Generated new resume version (v{new_version_num})",
        "resumeYaml": tailored_yaml,
        "filename": new_resume_filename
    }

@app.post("/applications/{app_id}/save-variables", response_model=Dict[str, str])
def save_variables(app_id: str, request: SaveVariablesRequest):
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

    final_vars = load_variables()
    custom_vars_path = os.path.join(app_path, "custom_variables.yaml")
    if os.path.exists(custom_vars_path):
        with open(custom_vars_path, 'r', encoding='utf-8') as f:
            app_specific_vars = yaml.safe_load(f)
            final_vars = merge_variables(final_vars, app_specific_vars)

    final_vars = merge_variables(final_vars, data.variables)

    pdf_path = os.path.join(app_path, "tailored_resume_preview.pdf")
    pdf_generator = ATSResumePDFGenerator(variables=final_vars)
    pdf_generator.generate_pdf_from_data(resume_data, pdf_path)
    
    return FileResponse(pdf_path, media_type='application/pdf', filename=f"{app_id}_resume_preview.pdf")

@app.post("/applications/{app_id}/finalize", response_model=Dict[str, str])
def finalize_resume(app_id: str, request: FinalizeRequest):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")

    try:
        resume_data = yaml.safe_load(request.resumeYaml)
        if 'name' not in resume_data:
            raise HTTPException(status_code=400, detail="Resume data must contain a 'name' field.")
    except yaml.YAMLError:
        raise HTTPException(status_code=400, detail="Invalid YAML format in resume data.")

    pdf_generator = ATSResumePDFGenerator(variables=request.variables)
    
    safe_name = "".join(c if c.isalnum() else '_' for c in resume_data['name'])
    final_pdf_name = f"Resume_{safe_name}.pdf"
    final_pdf_path = os.path.join(app_path, final_pdf_name)

    try:
        pdf_generator.generate_pdf_from_data(resume_data, final_pdf_path)
        return {"message": f"Successfully finalized resume as {final_pdf_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate final PDF: {str(e)}")
