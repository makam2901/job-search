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
You are an expert ATS resume writer and career coach. Your task is to transform a candidate's information into a high-impact, ATS-optimized resume that tells a compelling story of problem-solving heavily relevant to the job description. You can access the internet to help your decision-making for tailoring. You must output a valid JSON string.

**Target Job Description:**
---
{jd_text}
---

**Candidate's Fixed Information & Context (Use the 'context' field as a creative seed):**
```yaml
{fixed_resume_yaml}
```
---

**Your Task & Strict Instructions:**
Generate a JSON structure containing ONLY the following keys: `summary`, `skills_reordered`, `experience_bullets`, and `projects_reordered`.

1.  **`summary`**:
    - Write a powerful, 1-line professional summary (max 20 words) that perfectly mirrors the top requirements of the job description, optimized for ATS keyword matching.

2.  **`skills_reordered`**:
    - Reorder the skill category blocks from the fixed information based on their relevance to the job description. Do NOT change the content within each category.

3.  **`experience_bullets`**:
    - All the content should heavily be dependent on the job description.
    - Incoorporate the industry if mentioned in the job description. Ex: if finance is mentioned, invent saying financial data or financial reports.
    - This is your most critical task. You must generate bullet points using the **Problem-Action-Result (PAR)** framework.
    - For each bullet, you must first articulate the business **problem** or **challenge**, then the **action** taken, and finally the **quantifiable result**.
    - **INVENT QUANTIFIABLE METRICS.** Most bullets **MUST** include a plausible, impactful metric. Invent realistic ones if not provided. Examples: "reduced latency by 30%", "processed 500GB of data", "increased user engagement by 15%", "saved $50,000 in operational costs".
    - Word Count: 19 if small words, 17 if large words.
    - Number of Bullets:
        - DRINKS: 4 points
        - AB INBEV: 8 points
        - Janta Ka Mood: 2 points

4.  **`projects_reordered`**:
    - Reorder projects based on job relevance.
    - All the content should heavily be dependent on the job description.
    - For each project, write **two distinct types of bullet points**:
        - **Bullet 1 (The "Why"):** Focus on the **objective** or the **problem** this project was designed to solve. This should be more narrative and explain the project's purpose. It does not need a metric.
        - **Bullet 2 (The "How/What"):** Focus on the **technical implementation** and a **quantifiable result**. This bullet must contain a realistic, invented metric.
    - Word Count: 20 if small words, 18 if large words.
    - Number of Bullets: Exactly 2 for each project.
    - Include the original `title` and `dates` for each project.

**Output Format & Example:**
Your entire output MUST be a single, valid JSON string without any other text, explanations, or markdown. It must follow this exact structure:

```json
{{
  "summary": "A powerful, 1-line professional summary...",
  "skills_reordered": [
    {{ "ML_Techniques": ["Regression", "Classification", "..."] }},
    {{ "Cloud": ["AWS (Lambda, S3, Bedrock)", "..."] }}
  ],
  "experience_bullets": [
    {{
      "bullets": [
        "Addressed X challenge by implementing Y solution, achieving a 20% improvement in Z.",
        "Solved the problem of A by developing B, which processed 500GB of data daily.",
        "..."
      ]
    }}
  ],
  "projects_reordered": [
    {{
      "title": "AI Fantasy Team Predictor",
      "dates": "Mar 2025 - May 2025",
      "bullets": [
        "To provide cricket fans with a data-driven tool to create optimal fantasy teams and enhance engagement.",
        "Developed a GradientBoosting model and deployed it on GCP, improving prediction accuracy by over 95%."
      ]
    }}
  ]
}}
```
"""
    generated_content_str = call_gemini_api(prompt, is_json_output=True)
    
    cleaned_str = generated_content_str.replace("```json", "").replace("```", "").strip()
    return cleaned_str
