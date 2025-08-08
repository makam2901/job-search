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

# Import reportlab components needed for width calculation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.units import inch

# Import modularized functions and classes
from utils import get_app_id, APPLICATIONS_DIR, BASE_RESUME_PATH, load_variables, merge_variables
from llm_services import agent_resume_tailor, agent_cold_email_generator
from pdf_services import ATSResumePDFGenerator

# --- Load Environment Variables ---
load_dotenv()

# --- App Initialization ---
app = FastAPI(
    title="ApplySmart Backend",
    description="Manages job applications, renders PDFs, and generates cold emails.",
    version="17.0.0" # Version bump for data preprocessing
)

# --- CORS Middleware ---
origins = ["http://localhost:8080", "http://localhost"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class EmailDetails(BaseModel):
    to: str
    from_: str
    subject: str
    body: str

# --- Pydantic Models ---
class ApplicationData(BaseModel):
    companyName: str
    roleTitle: str
    jobId: Optional[str] = ""
    jobLink: Optional[str] = ""

class JobDescriptionData(BaseModel):
    htmlContent: str
    
class GenerateResumeRequest(BaseModel):
    modelProvider: str

class RenderRequestData(BaseModel):
    resumeYaml: str
    variables: Optional[Dict[str, Any]] = Field(None, description="Optional override for formatting variables")

class SaveVariablesRequest(BaseModel):
    variables: Dict[str, Any]

class FinalizeRequest(BaseModel):
    resumeYaml: str
    variables: Dict[str, Any]

class EmailGenerationRequest(BaseModel):
    recruiterName: Optional[str] = ""
    recruiterEmail: Optional[str] = ""
    recruiterLinkedIn: Optional[str] = ""
    additionalDetails: Optional[str] = ""
    modelProvider: str


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

def merge_resume_data(fixed_data: Dict, generated_data: Dict) -> Dict:
    """Merges the fixed and LLM-generated resume data."""
    final_resume = fixed_data.copy()

    if 'summary' in generated_data:
        final_resume['summary'] = generated_data['summary']
    
    if 'skills_reordered' in generated_data:
        final_resume['skills'] = generated_data['skills_reordered']
    elif 'skills' in fixed_data:
        final_resume['skills'] = fixed_data['skills']

    if 'experience_bullets' in generated_data and 'experience' in final_resume:
        for i, exp_bullets in enumerate(generated_data['experience_bullets']):
            if i < len(final_resume['experience']):
                final_resume['experience'][i]['bullets'] = exp_bullets.get('bullets', [])

    if 'projects_reordered' in generated_data:
        final_resume['projects'] = generated_data['projects_reordered']

    return final_resume

def update_app_details(app_path: str, new_details: Dict):
    """Reads, updates, and writes app_details.json."""
    details_path = os.path.join(app_path, "app_details.json")
    details = {}
    if os.path.exists(details_path):
        with open(details_path, 'r') as f:
            details = json.load(f)
    details.update(new_details)
    with open(details_path, 'w') as f:
        json.dump(details, f, indent=2)


# --- API Endpoints ---

# Save email details as YAML
@app.post("/applications/{app_id}/save-email-details")
async def save_email_details(app_id: str, details: EmailDetails):
    app_folder = os.path.join(APPLICATIONS_DIR, app_id)
    os.makedirs(app_folder, exist_ok=True)
    yaml_path = os.path.join(app_folder, "email_details.yaml")
    data = {"to": details.to, "from": details.from_, "subject": details.subject, "body": details.body}
    with open(yaml_path, "w") as f:
        yaml.dump(data, f)
    return {"message": "Email details saved successfully."}

# Fetch email details from YAML
@app.get("/applications/{app_id}/email-details")
async def get_email_details(app_id: str):
    yaml_path = os.path.join(APPLICATIONS_DIR, app_id, "email_details.yaml")
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Email details not found.")
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    return data
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
    
    details_path = os.path.join(app_path, "app_details.json")
    with open(details_path, 'w') as f:
        json.dump(data.dict(), f, indent=2)

    return {"message": "Application created successfully", "appId": app_id}

@app.get("/applications/{app_id}", response_model=Dict[str, Any])
def get_application_details(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path): raise HTTPException(status_code=404, detail="Application not found.")
    
    details_path = os.path.join(app_path, "app_details.json")
    jd_path = os.path.join(app_path, "job_description.html")
    
    resume_versions = get_resume_versions(app_path)
    latest_resume_file = resume_versions[0] if resume_versions else None
    yaml_path = os.path.join(app_path, latest_resume_file) if latest_resume_file else None

    details = {}
    if os.path.exists(details_path):
        with open(details_path, 'r') as f:
            details = json.load(f)

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

    finalized_pdf_path = os.path.join(app_path, f"Resume_{details.get('name', '').replace(' ', '_')}.pdf")
    
    return {
        "companyName": details.get("companyName"),
        "roleTitle": details.get("roleTitle"),
        "jobId": details.get("jobId"),
        "jobLink": details.get("jobLink"),
        "jobDescription": jd_content, 
        "resumeYaml": yaml_content, 
        "customVariables": custom_vars, 
        "resumeVersions": resume_versions,
        "emailDetails": {
            "recruiterName": details.get("recruiterName", ""),
            "recruiterEmail": details.get("recruiterEmail", ""),
            "recruiterLinkedIn": details.get("recruiterLinkedIn", ""),
            "additionalDetails": details.get("additionalDetails", "")
        },
        "finalizedPdfUrl": f"/applications/{app_id}/finalized-pdf" if os.path.exists(finalized_pdf_path) else None
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
def generate_resume(app_id: str, request: GenerateResumeRequest):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    jd_path = os.path.join(app_path, "job_description.html")
    if not os.path.exists(jd_path): raise HTTPException(status_code=404, detail="Job description not found.")

    with open(BASE_RESUME_PATH, 'r', encoding='utf-8') as f:
        fixed_resume_yaml = f.read()
        fixed_resume_data = yaml.safe_load(fixed_resume_yaml)

    with open(jd_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        jd_text = soup.get_text(separator='\n', strip=True)

    generated_content_str = agent_resume_tailor(jd_text, fixed_resume_yaml, request.modelProvider)
    
    try:
        generated_data = yaml.safe_load(generated_content_str)
    except yaml.YAMLError as e:
        print(f"Error parsing LLM response: {e}")
        print(f"LLM Response:\n{generated_content_str}")
        raise HTTPException(status_code=500, detail="Failed to parse LLM-generated resume content.")

    final_resume_data = merge_resume_data(fixed_resume_data, generated_data)
    final_resume_yaml = yaml.dump(final_resume_data, sort_keys=False, allow_unicode=True)

    resume_versions = get_resume_versions(app_path)
    version_numbers = [int(re.search(r'_v(\d+)\.yaml$', f).group(1)) for f in resume_versions if re.search(r'_v(\d+)\.yaml$', f)]
    new_version_num = max(version_numbers) + 1 if version_numbers else 1
    new_resume_filename = f"tailored_resume_v{new_version_num}.yaml"
    yaml_path = os.path.join(app_path, new_resume_filename)

    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(final_resume_yaml)

    updated_versions = get_resume_versions(app_path)

    return {
        "message": f"Generated new resume version (v{new_version_num})",
        "resumeYaml": final_resume_yaml,
        "filename": new_resume_filename,
        "resumeVersions": updated_versions
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

    if data.variables:
        final_vars = merge_variables(final_vars, data.variables)

    # Instantiate the generator
    pdf_generator = ATSResumePDFGenerator(variables=final_vars)
    
    # Create a dummy doc to get the width for preprocessing
    dummy_doc = SimpleDocTemplate(os.path.join(app_path, "dummy.pdf"), pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)

    # Preprocess the data to trim skills that would wrap
    trimmed_resume_data = pdf_generator.preprocess_data_for_fitting(resume_data, dummy_doc.width)

    pdf_path = os.path.join(app_path, "tailored_resume_preview.pdf")
    # Generate the PDF using the trimmed data
    pdf_generator.generate_pdf_from_data(trimmed_resume_data, pdf_path)
    
    if os.path.exists(os.path.join(app_path, "dummy.pdf")):
        os.remove(os.path.join(app_path, "dummy.pdf"))

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

    # Instantiate the generator with the final variables
    pdf_generator = ATSResumePDFGenerator(variables=request.variables)
    
    # Create a dummy doc to get the width for preprocessing
    dummy_doc = SimpleDocTemplate(os.path.join(app_path, "dummy.pdf"), pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)

    # Preprocess the data to trim skills that would wrap
    trimmed_resume_data = pdf_generator.preprocess_data_for_fitting(resume_data, dummy_doc.width)

    # Save the FINAL, TRIMMED YAML
    final_yaml_path = os.path.join(app_path, "finalized_resume.yaml")
    with open(final_yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(trimmed_resume_data, f, sort_keys=False, allow_unicode=True)

    # Generate the final PDF using the trimmed data
    safe_name = "".join(c if c.isalnum() else '_' for c in resume_data['name'])
    final_pdf_name = f"Resume_{safe_name}.pdf"
    final_pdf_path = os.path.join(app_path, final_pdf_name)

    try:
        pdf_generator.generate_pdf_from_data(trimmed_resume_data, final_pdf_path)
        # Update app_details with the name for easier retrieval later
        update_app_details(app_path, {"name": safe_name})
        if os.path.exists(os.path.join(app_path, "dummy.pdf")):
            os.remove(os.path.join(app_path, "dummy.pdf"))
        return {"message": f"Successfully finalized resume as {final_pdf_name}"}
    except Exception as e:
        if os.path.exists(os.path.join(app_path, "dummy.pdf")):
            os.remove(os.path.join(app_path, "dummy.pdf"))
        raise HTTPException(status_code=500, detail=f"Failed to generate final PDF: {str(e)}")

@app.get("/applications/{app_id}/finalized-pdf")
def get_finalized_pdf(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
    
    details_path = os.path.join(app_path, "app_details.json")
    if not os.path.exists(details_path):
        raise HTTPException(status_code=404, detail="Application details not found.")
        
    with open(details_path, 'r') as f:
        details = json.load(f)
    
    safe_name = details.get("name")
    if not safe_name:
        raise HTTPException(status_code=404, detail="Finalized resume name not found in details.")

    pdf_filename = f"Resume_{safe_name}.pdf"
    pdf_path = os.path.join(app_path, pdf_filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Finalized PDF not found.")
        
    return FileResponse(pdf_path, media_type='application/pdf', filename=pdf_filename)

@app.post("/applications/{app_id}/generate-email", response_model=Dict[str, str])
def generate_email(app_id: str, request: EmailGenerationRequest):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")

    # Save the provided email details to app_details.json
    update_app_details(app_path, request.dict(exclude={'modelProvider'}))

    # Load required content
    details_path = os.path.join(app_path, "app_details.json")
    jd_path = os.path.join(app_path, "job_description.html")
    resume_path = os.path.join(app_path, "finalized_resume.yaml")

    if not os.path.exists(details_path):
        raise HTTPException(status_code=404, detail="Application details not found.")
    if not os.path.exists(jd_path):
        raise HTTPException(status_code=404, detail="Job description not found. Please save it first.")
    if not os.path.exists(resume_path):
        raise HTTPException(status_code=404, detail="Finalized resume not found. Please finalize a resume version first.")

    with open(details_path, 'r') as f:
        app_details = json.load(f)
    
    with open(jd_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        jd_text = soup.get_text(separator='\n', strip=True)

    with open(resume_path, 'r', encoding='utf-8') as f:
        resume_yaml = f.read()

    # Call the LLM agent with all necessary context
    try:
        email_content_str = agent_cold_email_generator(
            company_name=app_details.get("companyName", ""),
            role_title=app_details.get("roleTitle", ""),
            recruiter_name=request.recruiterName,
            recipient_linkedin_url=request.recruiterLinkedIn,
            resume_yaml=resume_yaml,
            jd_text=jd_text,
            additional_details=request.additionalDetails,
            model_provider=request.modelProvider
        )
        email_content = json.loads(email_content_str)
        return email_content
    except Exception as e:
        print(f"Error during email generation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate email content: {e}")
