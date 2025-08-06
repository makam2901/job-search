import os
import google.generativeai as genai
import yaml
from fastapi import HTTPException
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# --- Configure the SDK ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def call_gemini_api(prompt: str, is_json_output: bool = False) -> str:
    """Calls the Gemini API. If is_json_output is True, it configures the model for JSON output."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable not set.")
    
    try:
        # Forcing JSON output for more reliable parsing
        generation_config = {
            "temperature": 0.7, 
            "top_p": 0.95, 
            "top_k": 64, 
            "max_output_tokens": 8192,
            "response_mime_type": "application/json"
        }

        # Define less restrictive safety settings to prevent erroneous blocking
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        model = genai.GenerativeModel(
            'gemini-2.5-pro', 
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        response = model.generate_content(prompt)
        
        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            finish_reason_name = "UNKNOWN"
            if response.candidates and hasattr(response.candidates[0].finish_reason, 'name'):
                finish_reason_name = response.candidates[0].finish_reason.name
            
            print(f"Gemini API call returned no content. Finish reason: {finish_reason_name}")
            print(f"Prompt feedback: {response.prompt_feedback}")
            
            error_detail = f"The model returned an empty response (Finish Reason: {finish_reason_name}). This may be due to safety filters or an issue with the prompt."
            raise HTTPException(status_code=500, detail=error_detail)

        return response.text

    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=503, detail=f"An error occurred with the Gemini API: {e}")


def agent_resume_tailor(jd_text: str, fixed_resume_yaml: str) -> str:
    """
    The Resume Tailoring Agent. It receives fixed resume data (with context) and a job description,
    and returns only the AI-generated content in a structured format.
    """
    prompt = f"""
You are an expert ATS resume writer with complete creative freedom. Your primary goal is to make the candidate the perfect fit for the job description by inventing compelling, tailored content. You must only output a valid JSON string.

**Target Job Description:**
---
{jd_text}
---

**Candidate's Fixed Information & Context (Use the 'context' field as a creative seed):**
```yaml
{fixed_resume_yaml}
```
---

**Your Task:**
Generate a JSON structure containing ONLY the following keys: `summary`, `experience_bullets`, and `projects_reordered`. Follow these instructions precisely:

1.  **`summary`**:
    - Write a powerful, 1 line professional summary that perfectly mirrors the top requirements of the job description optimized for ATS.

2.  **`experience_bullets`**:
    - This is a list of objects, each containing a `bullets` key. The list must correspond to the `experience` section in the fixed information.
    - You have **full creative freedom** to write bullet points. Use the `context` as a starting point, but invent realistic, quantifiable, and results-oriented achievements that directly align with the job description's needs.
    - Each bullet must be a single, impactful line. Start with a strong action verb.
    - it should be key word heavy based on job description and role in general what it demands.
    - content size:
        - DRINKS: 3 points
        - AB INBEV: 6 points
        - Janta Ka Mood: 2 points
    - Each bullet should be between 10-15 words. If absolutely necessary, you can go up to 20 words, but no more.

3.  **`projects_reordered`**:
    - Analyze the projects from the fixed information and the job description.
    - Reorder the projects to prioritize the ones most relevant to the job.
    - For each project in the newly ordered list, you must:
        - Include its original `title` and `dates`.
        - You have **full creative freedom** to write bullet points. Use the `context` as a starting point, but invent realistic, quantifiable, and results-oriented achievements that directly align with the job description's needs.
        - Each bullet must be a single, impactful line. Start with a strong action verb. (10-15 words)
        - it should be key word heavy based on job description and role in general what it demands.
        - only 2 for each project.
        - Each bullet should be between 10-15 words. If absolutely necessary, you can go up to 20 words, but no more.


**Output Format:**
Your entire output MUST be a single, valid JSON string. Do not include any other text, explanations, or markdown formatting like ```json.
"""
    generated_content_str = call_gemini_api(prompt, is_json_output=True)
    
    cleaned_str = generated_content_str.replace("```json", "").replace("```", "").strip()
    return cleaned_str
