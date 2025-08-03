import os
import google.generativeai as genai
from fastapi import HTTPException

# --- Configure the SDK ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def call_gemini_api(prompt: str, is_json_output: bool = False) -> str:
    """Calls the Gemini API. If is_json_output is True, it configures the model for JSON output."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable not set.")
    
    try:
        generation_config = {"temperature": 0.5, "top_p": 0.95, "top_k": 64, "max_output_tokens": 8192}
        if is_json_output:
            generation_config["response_mime_type"] = "application/json"

        model = genai.GenerativeModel('gemini-1.5-pro-latest', generation_config=generation_config)
        
        response = model.generate_content(prompt)
        
        text = response.text
        if is_json_output:
             text = text.replace("```json", "").replace("```", "").strip()
        return text
    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        raise HTTPException(status_code=503, detail=f"An error occurred with the Gemini API: {e}")


def agent_resume_tailor(jd_text: str, base_resume_yaml: str) -> str:
    """The Resume Tailoring Agent. Rewrites the entire resume for the target job."""
    prompt = f"""
You are an expert ATS resume writer. Your task is to rewrite the provided base resume (in YAML format) to be perfectly tailored for the target job description.

**Target Job Description:**
---
{jd_text}
---

**Base Resume YAML:**
---
{base_resume_yaml}
---

**Instructions:**
1.  Read the entire job description to understand the key requirements, skills, and qualifications.
2.  Rewrite the `summary` to be a powerful, 2-3 line professional summary that mirrors the top requirements of the job.
3.  Critically analyze the `experience` and `projects` sections. For each item, rewrite the `bullets` to be 2-4 crisp, impactful, single-line points.
    - Each bullet must be highly relevant to the job description, integrating its keywords naturally.
    - Start every bullet with a strong action verb (e.g., Architected, Implemented, Optimized).
    - Preserve and highlight quantitative metrics (e.g., $, %).
4.  Review the `skills` section. Re-categorize and refine the skills to match the technologies mentioned in the job description, while keeping the original structure.
5.  Maintain the original YAML structure of the base resume. Do not add or remove top-level keys.
6.  The output must be only the final, rewritten YAML content, without any extra explanations or formatting.
"""
    tailored_yaml_str = call_gemini_api(prompt, is_json_output=False)
    # Clean up potential markdown formatting from the response
    return tailored_yaml_str.replace("```yaml", "").replace("```", "").strip()
