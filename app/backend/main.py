# main.py
# To run this:
# 1. Install libraries: pip install fastapi uvicorn python-multipart "pyyaml[safe_loader]" reportlab beautifulsoup4 google-generativeai
# 2. Set your API Key: export GEMINI_API_KEY="YOUR_API_KEY"
# 3. Run the server from app/backend/: uvicorn main:app --reload

import os
import yaml
import json
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List
from bs4 import BeautifulSoup
import google.generativeai as genai

# PDF Rendering Imports
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.colors import black, blue
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle

# --- App Initialization ---
app = FastAPI(
    title="ApplySmart Backend",
    description="Manages job applications, generates ATS-optimized assets, and renders PDFs.",
    version="4.4.0" # Version bump for summary and formatting fixes
)

# --- CORS Middleware ---
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Pydantic Models ---
class ApplicationData(BaseModel):
    companyName: str
    roleTitle: str

class JobDescriptionData(BaseModel):
    htmlContent: str

# --- Constants ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
APPLICATIONS_DIR = os.path.join(PROJECT_ROOT, "applications")
BASE_RESUME_PATH = os.path.join(PROJECT_ROOT, "base_resume.json")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Configure the SDK ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- Helper Functions ---
def get_app_id(company_name: str, role_title: str) -> str:
    safe_company = company_name.replace(' ', '_').replace('/', '_')
    safe_role = role_title.replace(' ', '_').replace('/', '_')
    return f"{safe_company}_{safe_role}"

def call_gemini_api(prompt: str, is_json_output: bool = False) -> str:
    """Calls the Gemini API. If is_json_output is True, it configures the model for JSON output."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable not set.")
    
    try:
        generation_config = {"temperature": 0.5, "top_p": 0.95, "top_k": 64, "max_output_tokens": 8192}
        if is_json_output:
            generation_config["response_mime_type"] = "application/json"

        # *** Using the specified gemini-1.5-pro-latest model ***
        model = genai.GenerativeModel('gemini-2.5-pro', generation_config=generation_config)
        
        response = model.generate_content(prompt)
        
        text = response.text
        if is_json_output:
             text = text.replace("```json", "").replace("```", "").strip()
        return text
    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        raise HTTPException(status_code=503, detail=f"An error occurred with the Gemini API: {e}")

def render_resume_to_pdf(yaml_data: Dict, output_path: str):
    """Renders a resume from YAML data to a clean, ATS-FRIENDLY PDF based on the new format."""
    doc = SimpleDocTemplate(output_path, pagesize=letter,
                            rightMargin=0.5*inch, leftMargin=0.5*inch,
                            topMargin=0.25*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    
    # Using user-specified style for Name
    styles.add(ParagraphStyle(name='Name', fontName='Helvetica-Bold', fontSize=15, alignment=TA_CENTER, textColor=black, spaceAfter=10))
    
    styles.add(ParagraphStyle(name='Contact', fontName='Helvetica', fontSize=9, alignment=TA_CENTER, leading=5, textColor=black))
    styles.add(ParagraphStyle(name='Section', fontName='Helvetica-Bold', fontSize=11, alignment=TA_LEFT, spaceBefore=10, spaceAfter=4, textColor=black))
    styles.add(ParagraphStyle(name='Body', fontName='Helvetica', fontSize=9.5, alignment=TA_LEFT, leading=12, textColor=black))
    styles.add(ParagraphStyle(name='CustomBullet', fontName='Helvetica', fontSize=9.5, alignment=TA_LEFT, leading=12, leftIndent=12, bulletIndent=0, spaceAfter=2))
    styles.add(ParagraphStyle(name='InstTitle', fontName='Helvetica-Bold', fontSize=10, alignment=TA_LEFT, textColor=black))
    styles.add(ParagraphStyle(name='JobTitle', fontName='Helvetica-Bold', fontSize=10, alignment=TA_LEFT, textColor=black))
    styles.add(ParagraphStyle(name='JobDetails', fontName='Helvetica', fontSize=9, alignment=TA_LEFT, textColor=black, spaceAfter=4))
    styles.add(ParagraphStyle(name='SkillCategory', fontName='Helvetica-Bold', fontSize=9.5, alignment=TA_LEFT, leading=12))

    story = []
    contact = yaml_data.get('contact', {})
    story.append(Paragraph(contact.get('name', 'Name Missing').upper(), styles['Name']))
    
    # Using user-specified contact block
    contact_line_1 = f"""
        San Francisco, CA | 
        <font color="blue"><a href="mailto:makamsrimanikesh@outlook.com">makamsrimanikesh@outlook.com</a></font> | 
        <font color="blue"><a href="tel:+15512675388">+1 551-267-5388</a></font> | 
        <font color="blue"><a href="https://www.linkedin.com/in/manikesh-makam-31804a210/">LinkedIn</a></font> | 
        <font color="blue"><a href="https://github.com/makam2901">GitHub</a></font> | 
        <font color="blue"><a href="https://medium.com/@manikeshmakam">Medium</a></font>
        """
    story.append(Paragraph(contact_line_1, styles['Contact']))
    
    story.append(Paragraph("SUMMARY", styles['Section']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=black))
    story.append(Spacer(1, 4))
    story.append(Paragraph(yaml_data.get('summary', 'Summary could not be generated.'), styles['Body']))

    story.append(Paragraph("EDUCATION", styles['Section']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=black))
    for edu in yaml_data.get('education', []):
        story.append(Spacer(1, 4))
        data = [
                [Paragraph(edu.get('institution', '').upper(), styles['InstTitle']),
                Paragraph(edu.get('location', ''), styles['JobDetails'])],
                [Paragraph(f"<i>{edu.get('degree', '')}</i>", styles['Body']),
                Paragraph(edu.get('dates', ''), styles['JobDetails'])]
            ]

        # Stretch across the full width for better left-right spread
        table = Table(data, colWidths=[6.2*inch, 1.1*inch])
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),    # Ensure all rows in first column are left-aligned
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),   # Ensure all rows in second column are right-aligned
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))

        story.append(table)

    story.append(Paragraph("TECHNICAL SKILLS", styles['Section']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=black))
    story.append(Spacer(1, 4))
    skills_text = ""
    for skill_cat in yaml_data.get('skills', []):
        skills_text += f"<font name='Helvetica-Bold'>{skill_cat.get('category', '')}:</font> {', '.join(skill_cat.get('items', []))}<br/>"
    story.append(Paragraph(skills_text, styles['Body']))

    story.append(Paragraph("PROFESSIONAL EXPERIENCE", styles['Section']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=black))
    for job in yaml_data.get('experience', []):
        story.append(Spacer(1, 4))
        job_data = [
            [Paragraph(job.get('company', '').upper(), styles['InstTitle']),
             Paragraph(job.get('location', ''), styles['JobDetails'])],
            [Paragraph(f"<i>{job.get('title', '')}</i>", styles['Body']),
             Paragraph(job.get('dates', ''), styles['JobDetails'])]
        ]
        # Set colWidths to span the full document width (letter width 8.5" - 1" total margin = 7.5")
        job_table = Table(job_data, colWidths=[6.2*inch, 1.1*inch])
        job_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),    # Ensure all rows in first column are left-aligned
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),   # Ensure all rows in second column are right-aligned
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        story.append(job_table)
        for point in job.get('description', []):
            story.append(Paragraph(f"• {point}", styles['CustomBullet']))
        story.append(Spacer(1, 0.05*inch))

    story.append(Paragraph("PROJECTS", styles['Section']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=black))
    for proj in yaml_data.get('projects', []):
        story.append(Spacer(1, 4))
        story.append(Paragraph(proj.get('name', ''), styles['JobTitle']))
        for point in proj.get('description', []):
            story.append(Paragraph(f"• {point}", styles['CustomBullet']))
        story.append(Spacer(1, 0.05*inch))
    
    if 'certifications' in yaml_data and yaml_data.get('certifications'):
        story.append(Paragraph("CERTIFICATIONS", styles['Section']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=black))
        for cert in yaml_data.get('certifications', []):
            story.append(Spacer(1, 4))
            story.append(Paragraph(cert.get('name', ''), styles['JobTitle']))
            for point in cert.get('description', []):
                story.append(Paragraph(f"• {point}", styles['CustomBullet']))

    doc.build(story)
    print(f"PDF successfully rendered to {output_path}")

# --- Agentic Workflow Functions ---
def agent_content_writer(jd_text: str, content_block: Dict, content_type: str) -> List[str]:
    """The Content Writer Agent. Rewrites a single block of content for ATS optimization."""
    if content_type == "experience":
        prompt = f"""
You are an expert ATS resume writer. Rewrite the following job experience to be hyper-concise and keyword-rich for the target job description.

**Target Job Description:** {jd_text}
**Original Experience:** {json.dumps(content_block)}

**Instructions:**
1.  Rewrite the description into 2-3 crisp, impactful, single-line bullet points.
2.  Each point must be highly relevant to the job description, integrating its keywords.
3.  Ensure the points are distinct and non-overlapping.
4.  Start every bullet point with a strong action verb (e.g., Architected, Implemented, Optimized).
5.  Preserve all quantitative metrics (e.g., $, %).
6.  The output must be a JSON object with a single key "description" containing a list of the rewritten bullet points.
"""
    else: # Project
        prompt = f"""
You are an expert ATS resume writer. Rewrite the following project description to be hyper-concise and keyword-rich for the target job description.

**Target Job Description:** {jd_text}
**Original Project:** {json.dumps(content_block)}

**Instructions:**
1.  Rewrite the description into 1-2 crisp, impactful, single-line bullet points.
2.  Each point must be highly relevant to the job description, integrating its keywords.
3.  The output must be a JSON object with a single key "description" containing a list of the rewritten bullet points.
"""
    content_str = call_gemini_api(prompt, is_json_output=True)
    return json.loads(content_str)["description"]

def agent_skills_organizer(base_skills: List[Dict], jd_text: str) -> List[Dict]:
    """The Skills Organizer Agent. Creates a comprehensive, bucketed skills section."""
    prompt = f"""
You are a resume skills expert. Your task is to create a balanced and relevant skills section based on a job description.

**Existing Skills from Base Resume:** {json.dumps(base_skills)}
**Job Description:** {jd_text}

**Instructions:**
1.  Analyze the job description and extract the most important skills and technologies.
2.  Categorize these skills into logical buckets: "Programming Languages", "ML/DL Frameworks", "MLOps & Cloud", and "Data & Tools".
3.  Merge these categorized skills with the most relevant skills from the `Existing Skills`, ensuring no duplicates and a balanced final list. Do not "overuse" skills; find a good balance.
4.  The final output must be a JSON object with a single key "skills" which is a list of dictionaries, where each dictionary has a "category" and an "items" key.
"""
    skills_str = call_gemini_api(prompt, is_json_output=True)
    return json.loads(skills_str)["skills"]

def agent_summary_writer(jd_text: str) -> str:
    """Writes a keyword-dense summary for ATS optimization."""
    prompt = f"""
You are an expert ATS resume writer. Write a 2-3 line professional summary for a resume based on the target job description.

**Target Job Description:** {jd_text}

**Instructions:**
1.  Create a powerful summary that mirrors the top requirements of the job description.
2.  The summary must be keyword-rich and highly relevant.
3.  The output must be a JSON object with a single key "summary" containing the text.
"""
    summary_str = call_gemini_api(prompt, is_json_output=True)
    return json.loads(summary_str)["summary"]

# --- API Endpoints ---
@app.on_event("startup")
def on_startup():
    if not os.path.exists(APPLICATIONS_DIR): os.makedirs(APPLICATIONS_DIR)
    if not os.path.exists(BASE_RESUME_PATH): raise FileNotFoundError(f"'{BASE_RESUME_PATH}' not found.")

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

@app.get("/applications/{app_id}", response_model=Dict[str, str])
def get_application_details(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    if not os.path.exists(app_path): raise HTTPException(status_code=404, detail="Application not found.")
    jd_path = os.path.join(app_path, "job_description.html")
    yaml_path = os.path.join(app_path, "tailored_resume.yaml")
    jd_content = ""
    if os.path.exists(jd_path):
        with open(jd_path, 'r', encoding='utf-8') as f: jd_content = f.read()
    yaml_content = ""
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f: yaml_content = f.read()
    return {"jobDescription": jd_content, "resumeYaml": yaml_content}

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

    with open(BASE_RESUME_PATH, 'r') as f: base_resume = json.load(f)
    with open(jd_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        jd_text = soup.get_text(separator='\n', strip=True)

    # --- PRESCRIPTIVE WORKFLOW EXECUTION ---
    final_resume = {
        "contact": base_resume["contact"],
        "education": base_resume["education"],
        "skills": [],
        "experience": [],
        "projects": [],
        "certifications": base_resume["certifications"]
    }

    # *** FIX: Correctly call the summary agent and assign its output ***
    final_resume["summary"] = agent_summary_writer(jd_text)
    final_resume["skills"] = agent_skills_organizer(base_resume["skills"], jd_text)
    
    exp_to_include = ["DRINKS", "Anheuser-Busch InBev"]
    for exp in base_resume["experience"]:
        if exp["company"] in exp_to_include:
            new_desc = agent_content_writer(jd_text, exp, "experience")
            exp_copy = exp.copy()
            exp_copy["description"] = new_desc
            final_resume["experience"].append(exp_copy)

    projects_to_include = ["Parlay-and-Pray: AI Fantasy Team Predictor", "Annual Census Data Analysis", "Longitudinal Growth Prediction"]
    for proj in base_resume["projects"]:
        if proj["name"] in projects_to_include:
            new_desc = agent_content_writer(jd_text, proj, "project")
            proj_copy = proj.copy()
            proj_copy["description"] = new_desc
            final_resume["projects"].append(proj_copy)

    final_yaml_str = yaml.dump(final_resume, allow_unicode=True, sort_keys=False)
    yaml_path = os.path.join(app_path, "tailored_resume.yaml")
    with open(yaml_path, 'w', encoding='utf-8') as f: f.write(final_yaml_str)

    return {"message": "Resume generated successfully", "resumeYaml": final_yaml_str}

@app.post("/applications/{app_id}/render-pdf")
def render_pdf(app_id: str):
    app_path = os.path.join(APPLICATIONS_DIR, app_id)
    
    yaml_path = os.path.join(app_path, "tailored_resume.yaml")
    if not os.path.exists(yaml_path):
        print("YAML not found, generating it first...")
        generate_resume(app_id)

    with open(yaml_path, 'r', encoding='utf-8') as f: data = yaml.safe_load(f)
    
    pdf_path = os.path.join(app_path, "tailored_resume.pdf")
    render_resume_to_pdf(data, pdf_path)
    
    return FileResponse(pdf_path, media_type='application/pdf', filename=f"{app_id}_resume.pdf")
