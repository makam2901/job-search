import os
import yaml
import re
import json
import uuid
import copy
import shutil
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.units import inch

from utils import get_app_id, APPLICATIONS_DIR, BASE_RESUME_PATH, load_variables, merge_variables
from llm_services import agent_resume_tailor, agent_cold_email_generator, agent_cover_letter_generator
from pdf_services import ATSResumePDFGenerator, CoverLetterPDFGenerator

load_dotenv()

app = FastAPI(
    title="ApplySmart Backend",
    description="Manages job applications, renders PDFs, and generates cold emails.",
    version="22.0.0"
)

origins = ["http://localhost:8080", "http://localhost"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

TRACKER_APPS_PATH = os.path.join(APPLICATIONS_DIR, "tracker_applications.json")
TRACKER_EMAILS_PATH = os.path.join(APPLICATIONS_DIR, "tracker_emails.json")

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
    selections: Dict[str, Any]
    variables: Dict[str, Any]
    baseVersionFile: str

class EmailDetails(BaseModel):
    recruiterName: Optional[str] = ""
    recruiterEmail: Optional[str] = ""
    recruiterLinkedIn: Optional[str] = ""
    additionalDetails: Optional[str] = ""

class EmailGenerationRequest(BaseModel):
    recruiterName: Optional[str] = ""
    recruiterEmail: Optional[str] = ""
    recruiterLinkedIn: Optional[str] = ""
    additionalDetails: Optional[str] = ""
    modelProvider: str

class CoverLetterGenerationRequest(BaseModel):
    additionalDetails: Optional[str] = ""
    modelProvider: str

class SaveCoverLetterRequest(BaseModel):
    coverLetterText: str

class TrackerApplicationItem(BaseModel):
    id: str = Field(default_factory=lambda: f"app_{uuid.uuid4().hex}")
    company: str
    role: str
    jobId: Optional[str] = ""
    referral: bool = False
    contact: Optional[str] = ""
    status: str = "To Apply"
    jobLink: Optional[str] = ""
    statusLink: Optional[str] = ""
    createdAt: str = Field(default_factory=lambda: datetime.now().isoformat())
    lastUpdatedAt: Optional[str] = None

class TrackerEmailItem(BaseModel):
    id: str = Field(default_factory=lambda: f"email_{uuid.uuid4().hex}")
    company: str
    role: str
    jobId: Optional[str] = ""
    recruiter: Optional[str] = ""
    contact: Optional[str] = ""
    status: str = "Sent"
    jobLink: Optional[str] = ""
    createdAt: str = Field(default_factory=lambda: datetime.now().isoformat())

class TrackEmailRequest(BaseModel):
    recruiterName: str
    recruiterEmail: str

def update_application_timestamp(app_id: str):
    """Updates the modification time of the application directory."""
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if os.path.isdir(app_path):
        try:
            os.utime(app_path, None)
        except OSError as e:
            print(f"Could not update timestamp for {app_path}: {e}")

def get_resume_versions(app_path: str) -> List[str]:
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
    details_path = os.path.join(app_path, "app_details.json")
    details = {}
    if os.path.exists(details_path):
        with open(details_path, 'r') as f:
            try:
                details = json.load(f)
            except json.JSONDecodeError:
                details = {}
    details.update(new_details)
    with open(details_path, 'w') as f:
        json.dump(details, f, indent=2)

def read_tracker_data(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def write_tracker_data(path: str, data: List[Dict]):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def filter_resume_data(data: Dict, selections: Dict) -> Dict:
    filtered_data = copy.deepcopy(data)

    if 'contact' in filtered_data:
        if 'contact-email' in selections:
            filtered_data['contact']['email'] = selections['contact-email']
        if 'contact-location' in selections:
            filtered_data['contact']['location'] = selections['contact-location']

    sections_to_process = ['summary', 'skills', 'education', 'experience', 'projects']
    for section_key in sections_to_process:
        if section_key not in filtered_data:
            continue

        if not selections.get(f'select-{section_key}', True):
            del filtered_data[section_key]
            continue

        if isinstance(filtered_data.get(section_key), list):
            filtered_items = []
            for i, item in enumerate(data[section_key]):
                item_key = f'select-{section_key}-{i}'
                if selections.get(item_key, True):
                    filtered_items.append(item)
            
            if not filtered_items:
                 del filtered_data[section_key]
            else:
                filtered_data[section_key] = filtered_items

    return filtered_data

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
                "jobId": details.get("jobId"),
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
                    "jobId": "",
                    "createdAt": created_at 
                })
            except ValueError:
                continue
            
    apps.sort(key=lambda x: x['createdAt'], reverse=True)
    return apps

@app.post("/applications", response_model=Dict[str, str])
def create_application(data: ApplicationData):
    app_id = get_app_id(data.companyName, data.roleTitle, data.jobId)
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
    
    details = {}
    if os.path.exists(details_path):
        with open(details_path, 'r') as f:
            details = json.load(f)

    resume_versions = get_resume_versions(app_path)
    
    finalized_base_version = details.get("finalizedBaseVersion")
    if finalized_base_version and os.path.exists(os.path.join(app_path, finalized_base_version)):
        base_version_file = finalized_base_version
    else:
        base_version_file = resume_versions[0] if resume_versions else None

    yaml_path = os.path.join(app_path, base_version_file) if base_version_file else None

    yaml_content = ""
    if yaml_path and os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f: yaml_content = f.read()

    jd_content = ""
    if os.path.exists(jd_path):
        with open(jd_path, 'r', encoding='utf-8') as f: jd_content = f.read()

    finalized_yaml_path = os.path.join(app_path, "finalized_resume.yaml")
    finalized_yaml_content = ""
    if os.path.exists(finalized_yaml_path):
        with open(finalized_yaml_path, 'r', encoding='utf-8') as f:
            finalized_yaml_content = f.read()

    custom_vars_path = os.path.join(app_path, "custom_variables.yaml")
    custom_vars = None
    if os.path.exists(custom_vars_path):
        with open(custom_vars_path, 'r', encoding='utf-8') as f:
            custom_vars = yaml.safe_load(f)

    finalized_pdf_path = os.path.join(app_path, f"Resume_{details.get('name', '').replace(' ', '_')}.pdf")
    finalized_cover_letter_file = details.get("finalizedCoverLetterFile")
    
    return {
        "companyName": details.get("companyName"),
        "roleTitle": details.get("roleTitle"),
        "jobId": details.get("jobId"),
        "jobLink": details.get("jobLink"),
        "jobDescription": jd_content, 
        "resumeYaml": yaml_content,
        "finalizedResumeYaml": finalized_yaml_content,
        "customVariables": custom_vars, 
        "resumeVersions": resume_versions,
        "emailDetails": {
            "recruiterName": details.get("recruiterName", ""),
            "recruiterEmail": details.get("recruiterEmail", ""),
            "recruiterLinkedIn": details.get("recruiterLinkedIn", ""),
            "additionalDetails": details.get("additionalDetails", ""),
            "generatedEmailSubject": details.get("generatedEmailSubject", ""),
            "generatedEmailBody": details.get("generatedEmailBody", "")
        },
        "coverLetter": {
            "additionalDetails": details.get("coverLetterAdditionalDetails", ""),
            "generatedBody": details.get("generatedCoverLetterBody", ""),
            "pdfUrl": f"/applications/{app_id}/cover-letter-pdf" if finalized_cover_letter_file and os.path.exists(os.path.join(app_path, finalized_cover_letter_file)) else None
        },
        "finalizedPdfUrl": f"/applications/{app_id}/finalized-pdf" if os.path.exists(finalized_pdf_path) else None
    }

@app.get("/applications/{app_id}/resume-content", response_model=Dict)
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
    update_application_timestamp(app_id)
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

    update_application_timestamp(app_id)
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
        update_application_timestamp(app_id)
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

    pdf_generator = ATSResumePDFGenerator(variables=final_vars)
    
    dummy_doc = SimpleDocTemplate(os.path.join(app_path, "dummy.pdf"), pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)

    trimmed_resume_data = pdf_generator.preprocess_data_for_fitting(resume_data, dummy_doc.width)

    pdf_path = os.path.join(app_path, "tailored_resume_preview.pdf")
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
        original_data = yaml.safe_load(request.resumeYaml)
    except yaml.YAMLError:
        raise HTTPException(status_code=400, detail="Invalid YAML format in request resume data.")

    final_resume_data = filter_resume_data(original_data, request.selections)
    
    if 'name' not in final_resume_data:
        if 'name' in original_data:
            final_resume_data['name'] = original_data['name']
        else:
            raise HTTPException(status_code=400, detail="Resume data must contain a 'name' field.")

    final_yaml_path = os.path.join(app_path, "finalized_resume.yaml")
    with open(final_yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(final_resume_data, f, sort_keys=False, allow_unicode=True)

    try:
        pdf_generator = ATSResumePDFGenerator(variables=request.variables)
        
        dummy_doc = SimpleDocTemplate(os.path.join(app_path, "dummy_for_width.pdf"), pagesize=letter, rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.4*inch, bottomMargin=0.4*inch)
        
        trimmed_resume_data = pdf_generator.preprocess_data_for_fitting(final_resume_data, dummy_doc.width)

        safe_name = "".join(c if c.isalnum() else '_' for c in final_resume_data.get('name', ''))
        final_pdf_name = f"Resume_{safe_name}.pdf"
        final_pdf_path = os.path.join(app_path, final_pdf_name)

        pdf_generator.generate_pdf_from_data(trimmed_resume_data, final_pdf_path)

        update_app_details(app_path, {
            "name": safe_name,
            "finalizedBaseVersion": request.baseVersionFile
        })
        
        if os.path.exists(dummy_doc.filename):
            os.remove(dummy_doc.filename)

        update_application_timestamp(app_id)
        return {"message": f"Successfully finalized resume as {final_pdf_name}."}
        
    except Exception as e:
        dummy_path = os.path.join(app_path, "dummy_for_width.pdf")
        if os.path.exists(dummy_path):
            os.remove(dummy_path)
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

@app.post("/applications/{app_id}/save-email-details", response_model=Dict[str, str])
def save_email_details(app_id: str, details: EmailDetails):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
    
    update_app_details(app_path, details.dict())
    update_application_timestamp(app_id)
    return {"message": "Email details saved."}

@app.post("/applications/{app_id}/generate-email", response_model=Dict[str, str])
def generate_email(app_id: str, request: EmailGenerationRequest):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")

    details_path = os.path.join(app_path, "app_details.json")
    jd_path = os.path.join(app_path, "job_description.html")
    resume_path = os.path.join(app_path, "finalized_resume.yaml")

    if not os.path.exists(details_path): raise HTTPException(status_code=404, detail="Application details not found.")
    if not os.path.exists(jd_path): raise HTTPException(status_code=404, detail="Job description not found.")
    if not os.path.exists(resume_path): raise HTTPException(status_code=404, detail="Finalized resume not found.")

    with open(details_path, 'r') as f: app_details = json.load(f)
    with open(jd_path, 'r', encoding='utf-8') as f: jd_text = BeautifulSoup(f.read(), 'html.parser').get_text(separator='\n', strip=True)
    with open(resume_path, 'r', encoding='utf-8') as f: resume_yaml = f.read()

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
        
        details_to_save = request.dict(exclude={'modelProvider'})
        details_to_save['generatedEmailSubject'] = email_content.get('subject')
        details_to_save['generatedEmailBody'] = email_content.get('body')
        
        update_app_details(app_path, details_to_save)
        update_application_timestamp(app_id)
        return email_content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate email content: {e}")
    
@app.post("/applications/{app_id}/generate-cover-letter", response_model=Dict[str, str])
def generate_cover_letter(app_id: str, request: CoverLetterGenerationRequest):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")

    jd_path = os.path.join(app_path, "job_description.html")
    resume_path = os.path.join(app_path, "finalized_resume.yaml")

    if not os.path.exists(jd_path): raise HTTPException(status_code=404, detail="Job description not found.")
    if not os.path.exists(resume_path): raise HTTPException(status_code=404, detail="A finalized resume is required to generate a cover letter.")

    with open(jd_path, 'r', encoding='utf-8') as f:
        jd_text = BeautifulSoup(f.read(), 'html.parser').get_text(separator='\n', strip=True)
    with open(resume_path, 'r', encoding='utf-8') as f:
        resume_yaml = f.read()
    
    try:
        cover_letter_str = agent_cover_letter_generator(
            resume_yaml=resume_yaml,
            jd_text=jd_text,
            additional_details=request.additionalDetails,
            model_provider=request.modelProvider
        )
        cover_letter_content = json.loads(cover_letter_str)
        body = cover_letter_content.get("cover_letter_body", "")

        update_app_details(app_path, {
            "coverLetterAdditionalDetails": request.additionalDetails,
            "generatedCoverLetterBody": body
        })
        update_application_timestamp(app_id)
        return {"cover_letter_body": body}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate cover letter: {str(e)}")

@app.post("/applications/{app_id}/save-cover-letter", response_model=Dict[str, str])
def save_cover_letter(app_id: str, request: SaveCoverLetterRequest):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
    
    try:
        with open(BASE_RESUME_PATH, 'r', encoding='utf-8') as f:
            base_resume_data = yaml.safe_load(f)
        
        contact_info = base_resume_data.get('contact', {})
        candidate_name = base_resume_data.get('name', 'Candidate')
        safe_name = "".join(c if c.isalnum() else '_' for c in candidate_name)
        
        final_pdf_name = f"CoverLetter_{safe_name}.pdf"
        pdf_path = os.path.join(app_path, final_pdf_name)

        update_app_details(app_path, {
            "generatedCoverLetterBody": request.coverLetterText,
            "finalizedCoverLetterFile": final_pdf_name
        })

        variables = load_variables()
        pdf_generator = CoverLetterPDFGenerator(variables=variables)
        pdf_generator.generate_pdf(request.coverLetterText, contact_info, pdf_path, candidate_name)
        update_application_timestamp(app_id)
        return {"message": "Cover letter saved and PDF updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save cover letter: {str(e)}")

@app.get("/applications/{app_id}/cover-letter-pdf")
def get_cover_letter_pdf(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.isdir(app_path):
        raise HTTPException(status_code=404, detail="Application not found.")
    
    details_path = os.path.join(app_path, "app_details.json")
    if not os.path.exists(details_path):
        raise HTTPException(status_code=404, detail="Application details not found.")
        
    with open(details_path, 'r') as f:
        details = json.load(f)
    
    pdf_filename = details.get("finalizedCoverLetterFile")
    if not pdf_filename:
        raise HTTPException(status_code=404, detail="Finalized cover letter not found in details.")

    pdf_path = os.path.join(app_path, pdf_filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Cover Letter PDF file not found on disk.")
        
    return FileResponse(pdf_path, media_type='application/pdf', filename=pdf_filename)

@app.post("/applications/{app_id}/track-application", response_model=TrackerApplicationItem)
def track_application(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    details_path = os.path.join(app_path, "app_details.json")
    if not os.path.exists(details_path):
        raise HTTPException(status_code=404, detail="Application details not found.")

    with open(details_path, 'r') as f:
        details = json.load(f)

    finalized_resume_path = os.path.join(app_path, "finalized_resume.yaml")
    status = "Ready to Apply" if os.path.exists(finalized_resume_path) else "To Apply"

    apps = read_tracker_data(TRACKER_APPS_PATH)

    company = details.get("companyName", "")
    role = details.get("roleTitle", "")
    jobId = details.get("jobId", "")
    jobLink = details.get("jobLink", "")

    existing_item = next((item for item in apps if item.get("company") == company and item.get("role") == role and item.get("jobId") == jobId), None)

    if existing_item:
        existing_item["jobLink"] = jobLink
        existing_item["status"] = status
        write_tracker_data(TRACKER_APPS_PATH, apps)
        return existing_item
    else:
        new_app_item = TrackerApplicationItem(
            company=company,
            role=role,
            jobId=jobId,
            jobLink=jobLink,
            status=status
        )
        apps.insert(0, new_app_item.dict())
        write_tracker_data(TRACKER_APPS_PATH, apps)
        return new_app_item

@app.get("/tracker/applications", response_model=List[TrackerApplicationItem])
def get_tracker_applications():
    apps_data = read_tracker_data(TRACKER_APPS_PATH)
    for app in apps_data:
        app_id = get_app_id(app.get("company"), app.get("role"), app.get("jobId"))
        app_path = os.path.join(APPLICATIONS_DIR, app_id)
        if os.path.isdir(app_path):
            mtime = os.path.getmtime(app_path)
            app["lastUpdatedAt"] = datetime.fromtimestamp(mtime).isoformat()
        else:
            app["lastUpdatedAt"] = app.get("createdAt")
    return apps_data

@app.post("/tracker/applications", response_model=TrackerApplicationItem)
def add_tracker_application(item: TrackerApplicationItem):
    apps = read_tracker_data(TRACKER_APPS_PATH)
    
    app_id = get_app_id(item.company, item.role, item.jobId)
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.exists(app_path):
        os.makedirs(app_path)
        details_path = os.path.join(app_path, "app_details.json")
        with open(details_path, 'w') as f:
            json.dump({
                "companyName": item.company,
                "roleTitle": item.role,
                "jobId": item.jobId,
                "jobLink": item.jobLink
            }, f, indent=2)

    existing_item = next((app for app in apps if app.get("company") == item.company and app.get("role") == item.role and app.get("jobId") == item.jobId), None)

    if existing_item:
        for key, value in item.dict(exclude_unset=True).items():
            existing_item[key] = value
        write_tracker_data(TRACKER_APPS_PATH, apps)
        return existing_item
    else:
        apps.insert(0, item.dict())
        write_tracker_data(TRACKER_APPS_PATH, apps)
        return item

@app.put("/tracker/applications/{item_id}", response_model=TrackerApplicationItem)
def update_tracker_application(item_id: str, updated_item: TrackerApplicationItem):
    apps = read_tracker_data(TRACKER_APPS_PATH)
    index = next((i for i, app in enumerate(apps) if app["id"] == item_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Application item not found")
    
    original_created_at = apps[index].get("createdAt", datetime.now().isoformat())
    item_dict = updated_item.dict(exclude_unset=True)
    
    apps[index].update(item_dict)
    apps[index]["createdAt"] = original_created_at
    apps[index]["id"] = item_id

    app_id = get_app_id(apps[index].get("company"), apps[index].get("role"), apps[index].get("jobId"))
    update_application_timestamp(app_id)

    write_tracker_data(TRACKER_APPS_PATH, apps)
    return apps[index]

@app.delete("/tracker/applications/{item_id}", status_code=204)
def delete_tracker_application(item_id: str):
    apps = read_tracker_data(TRACKER_APPS_PATH)
    app_to_delete = next((app for app in apps if app["id"] == item_id), None)
    
    if not app_to_delete:
        raise HTTPException(status_code=404, detail="Application item not found in tracker.")

    app_id = get_app_id(app_to_delete['company'], app_to_delete['role'], app_to_delete.get('jobId'))
    app_path = os.path.join(APPLICATIONS_DIR, app_id)

    if os.path.isdir(app_path):
        try:
            shutil.rmtree(app_path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete application folder: {e}")

    updated_apps = [app for app in apps if app["id"] != item_id]
    write_tracker_data(TRACKER_APPS_PATH, updated_apps)
    
    return

@app.get("/tracker/emails", response_model=List[TrackerEmailItem])
def get_tracker_emails():
    return read_tracker_data(TRACKER_EMAILS_PATH)

@app.post("/applications/{app_id}/track-email", response_model=TrackerEmailItem)
def track_email(app_id: str, request: TrackEmailRequest):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    details_path = os.path.join(app_path, "app_details.json")
    if not os.path.exists(details_path):
        raise HTTPException(status_code=404, detail="Application details not found.")
    
    with open(details_path, 'r') as f:
        details = json.load(f)

    emails = read_tracker_data(TRACKER_EMAILS_PATH)
    
    company = details.get("companyName", "")
    role = details.get("roleTitle", "")
    jobId = details.get("jobId", "")
    jobLink = details.get("jobLink", "")

    existing_item_index = -1
    if jobId and jobId.strip():
        existing_item_index = next((i for i, item in enumerate(emails) if item.get("jobId") == jobId), -1)
    
    if existing_item_index == -1:
        existing_item_index = next((i for i, item in enumerate(emails) if item.get("company") == company and item.get("role") == role), -1)

    if existing_item_index != -1:
        emails[existing_item_index]["recruiter"] = request.recruiterName
        emails[existing_item_index]["contact"] = request.recruiterEmail
        emails[existing_item_index]["jobLink"] = jobLink
        emails[existing_item_index]["jobId"] = jobId
        emails[existing_item_index]["status"] = "Sent"
        write_tracker_data(TRACKER_EMAILS_PATH, emails)
        return emails[existing_item_index]
    else:
        new_email_item = TrackerEmailItem(
            company=company,
            role=role,
            jobId=jobId,
            recruiter=request.recruiterName,
            contact=request.recruiterEmail,
            status="Sent",
            jobLink=jobLink
        )
        emails.insert(0, new_email_item.dict())
        write_tracker_data(TRACKER_EMAILS_PATH, emails)
        return new_email_item

@app.put("/tracker/emails/{item_id}", response_model=TrackerEmailItem)
def update_tracker_email(item_id: str, updated_item: TrackerEmailItem):
    emails = read_tracker_data(TRACKER_EMAILS_PATH)
    index = next((i for i, email in enumerate(emails) if email["id"] == item_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Email item not found")
    
    original_created_at = emails[index].get("createdAt", datetime.now().isoformat())
    item_dict = updated_item.dict()
    item_dict["createdAt"] = original_created_at
    item_dict["id"] = item_id

    emails[index] = item_dict
    write_tracker_data(TRACKER_EMAILS_PATH, emails)
    return emails[index]

@app.delete("/tracker/emails/{item_id}", status_code=204)
def delete_tracker_email(item_id: str):
    emails = read_tracker_data(TRACKER_EMAILS_PATH)
    initial_len = len(emails)
    emails = [email for email in emails if email["id"] != item_id]
    if len(emails) == initial_len:
        raise HTTPException(status_code=404, detail="Email item not found")
    write_tracker_data(TRACKER_EMAILS_PATH, emails)
    return
