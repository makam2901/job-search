import os
import google.generativeai as genai
from openai import OpenAI
import yaml
import json
from fastapi import HTTPException
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# --- Configure the SDKs ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

OPEN_ROUTER_KEY = os.getenv("OPEN_ROUTER_KEY")

# --- API Call Functions ---

def call_gemini_api(prompt: str, is_json_output: bool = False) -> str:
    """Calls the Google Gemini API."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable not set.")
    
    try:
        generation_config = {
            "temperature": 0.7, 
            "top_p": 0.95, 
            "top_k": 64, 
            "max_output_tokens": 8192,
        }
        if is_json_output:
            generation_config["response_mime_type"] = "application/json"

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
            
            error_detail = f"The model returned an empty response (Finish Reason: {finish_reason_name})."
            raise HTTPException(status_code=500, detail=error_detail)

        return response.text

    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=503, detail=f"An error occurred with the Gemini API: {e}")

def call_openrouter_api(prompt: str, is_json_output: bool = False) -> str:
    """Calls the OpenRouter API using the OpenAI SDK."""
    if not OPEN_ROUTER_KEY:
        raise HTTPException(status_code=500, detail="OPEN_ROUTER_KEY environment variable not set.")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPEN_ROUTER_KEY,
    )
    
    try:
        messages = [{"role": "user", "content": prompt}]
        
        response_format = {"type": "json_object"} if is_json_output else {"type": "text"}

        response = client.chat.completions.create(
            model="openai/gpt-3.5-turbo", # You can change this to other models supported by OpenRouter
            messages=messages,
            response_format=response_format
        )
        
        content = response.choices[0].message.content
        if not content:
             raise HTTPException(status_code=500, detail="The model returned an empty response from OpenRouter.")
        
        return content

    except Exception as e:
        print(f"An error occurred with the OpenRouter API: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=503, detail=f"An error occurred with the OpenRouter API: {e}")


# --- Agent Definitions ---

def agent_resume_tailor(jd_text: str, fixed_resume_yaml: str, model_provider: str = "gemini") -> str:
    """
    The Resume Tailoring Agent. It receives fixed resume data (with context) and a job description,
    and returns only the AI-generated content in a structured format.
    """
    prompt = f"""
You are an expert ATS resume architect and career strategist. Your sole function is to deconstruct a target job description and completely re-engineer a candidate's information into a high-impact ATS optimized resume. Your primary directive is to make the candidate appear as the perfect-fit applicant by strategically inventing and aligning their experience with the role's requirements. You must output a valid JSON string.

**Target Job Description:**
---
{jd_text}
---

**Candidate's Base Information & Context (Use as a creative seed):**
```yaml
{fixed_resume_yaml}
```
---

**Your Task & Strict Instructions:**
Generate a JSON structure containing ONLY the following keys: `summary`, `skills_reordered`, `experience_bullets`, and `projects_reordered`.

1.  **`summary`**:
    - Write a powerful, 1-line professional summary (max 20 words, entire line must be under 140 characters) that perfectly mirrors the top requirements of the job description. State the candidate has 3 years of experience.

2.  **`skills_reordered`**:
    - **Reorder the skill category blocks** from the fixed information based on their relevance to the job description. Retain all categories.
    - **Reorder the individual skills within each category** to prioritize those most relevant to the job description first.
    - **Identify skills mentioned in the job description that are missing** from the candidate's list but are relevant to their profile. Make sure you are not repeating skills across the categories as well.
    - **Insert these new, relevant skills into the most appropriate existing categories**, maintaining the relevance-based order. Do NOT create new categories.

3.  **`experience_bullets`**:
    - **Re-engineer from scratch:** Do NOT just rephrase the context from the YAML. Your task is to **invent new, highly relevant bullet points** that directly address the challenges and requirements of the job description.
    - **Inject industry context:** If the job description mentions a specific industry (e.g., finance, healthcare), you MUST invent details reflecting that context (e.g., "analyzed financial reports," "processed patient data") only if it aligns with the context. For example: there can be financial reports in beverages company, but it wont have access to healthcare records right.
    - For majority bullets, you must first articulate the business **problem** or **challenge**, then the **action** taken, and finally the **quantifiable result**.
    - **INVENT QUANTIFIABLE METRICS.** For majority bullets **MUST** include a plausible, impactful metric. Invent realistic ones if not provided. Examples: "reduced latency by 30%", "processed 500GB of data", "increased user engagement by 15%", "saved $50,000 in operational costs".
    - Word Count: make the entire line is 135 characters. strict.
    - **Strategic Bolding**: Identify the most critical parts of each bullet points based on the bullet itself and the job description. Wrap these keywords in `<b>...</b>` tags. Use this sparingly—aim for 1-3 bolded phrases per bullet to maximize impact without cluttering the text. Dont focus on the reseults always. Highlighting actions are also important.
    - Number of Bullets:
        - DRINKS: 4 points
        - AB INBEV: 8 points
        - Janta Ka Mood: 2 points
    - Example: if JD require experience with Databricks, etc. then make sure you include that in the bullet points.

4.  **`projects_reordered`**:
    - **Follow all rules from the `experience_bullets` section:** Re-engineer the content to be heavily job-description-focused, inject industry context, use the PAR framework, and invent compelling, quantifiable metrics for each bullet.
    - Keep the original `title` and `dates` for each project.
    - Each bullet must be under 140 characters.
    - Use strategic `<b>...</b>` bolding.
    - Only 2 bullets per project.
    - **You MUST process and return ALL projects** provided in the candidate's base information.
    - Reorder the projects based on the relevance of generated bullets to the job description.

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
    if model_provider == "chatgpt":
        generated_content_str = call_openrouter_api(prompt, is_json_output=True)
    else: # Default to gemini
        generated_content_str = call_gemini_api(prompt, is_json_output=True)
    
    cleaned_str = generated_content_str.replace("```json", "").replace("```", "").strip()
    return cleaned_str

def agent_cold_email_generator(company_name: str, role_title: str, recruiter_name: str, recipient_linkedin_url: str, resume_yaml: str, jd_text: str, additional_details: str, model_provider: str = "gemini") -> str:
    """
    The Cold Email Agent. It receives contact/job info and a finalized resume,
    researches online, and generates a personalized cold email.
    """
    prompt = f"""
You are an expert career coach and copywriter specializing in crafting compelling cold emails for job applications. Your task is to generate a personalized email to a contact person at a company. You MUST use the internet to perform research to make the email as impactful as possible.

**Your Goal:**
Write an email that is professional, concise, highly personalized, and grabs the contact's attention, making them want to learn more about the candidate. The email should tell a compelling story, not just list facts.

**Input Information:**
1.  **Company Name:** {company_name}
2.  **Role Title:** {role_title}
3.  **Contact Name:** {recruiter_name if recruiter_name else "Not Provided"}
4.  **Contact's LinkedIn Profile:** {recipient_linkedin_url if recipient_linkedin_url else "Not Provided"}
5.  **Candidate's Finalized Resume (YAML format):**
    ```yaml
    {resume_yaml}
    ```
6.  **Target Job Description:**
    ---
    {jd_text}
    ---
7.  **Additional Details from User:** {additional_details if additional_details else "None"}

**Your Multi-Step Task & Strict Instructions:**

**Step 1: Research Contact Person (LinkedIn Analysis)**
- If a LinkedIn profile is provided, **you must visit the URL**.
- Analyze the contact's profile for:
    - Their professional background, expertise, and specific role.
    - Recent posts, articles, or comments they've made that you can genuinely connect with.
    - Shared connections, groups, or alma maters.
    - The company's recent news or projects they might be involved in.
- Your goal is to find a **genuine, non-generic** point of connection to mention in the email's opening. This is critical for personalization.

**Step 2: Synthesize and Write a Compelling Narrative**
- Based on all the information gathered, write the email.
- **Subject Line:** You MUST use one of these two formats: "Inquiry regarding {role_title} at {company_name}" or "Interested in the {role_title} role at {company_name}". Choose one.
- **Tone:** Confident, respectful, and enthusiastic. No em dashes or no hyphenated words.
- **Structure:**
    - **Opener:** Start with a highly personalized hook based on your deep LinkedIn research (e.g., "I was impressed by your recent article on the future of AI in finance..." or "I noticed we both share an interest in scalable cloud architectures..."). If no LinkedIn is provided, use a polite, direct opening.
    - **Introduction:** Briefly introduce the candidate and clearly state the purpose of the email – expressing interest in the **{role_title}** position at **{company_name}**.
    - **The "Why" - Create a Narrative:** This is the most important part. Do not just list skills. Weave a compelling 1-2 paragraph story. Connect the candidate's key experiences from their resume to the most critical requirements in the job description. For example, instead of saying "Reduced latency by 30%", say "At my previous role, I tackled the challenge of slow data processing by architecting a new ETL pipeline, which ultimately reduced latency by 30% and unlocked new analytics capabilities." Frame their skills as solutions to the problems mentioned in the JD.
    - **Call to Action:** Propose a brief chat to discuss the role further. Make it easy for them by suggesting a specific action (e.g., "Are you available for a brief chat to discuss how my background in [mention 1-2 key skills] could support the team at {company_name}?").
    - **Closing:** A professional closing (e.g., "Best regards,").

**Step 3: Generate Output**
- Your entire output MUST be a single, valid JSON string with no other text, explanations, or markdown.
- The JSON object must contain two keys: `subject` and `body`.
- The `body` should be a single string with newline characters (`\\n`) for paragraph breaks.

**Output Format & Example:**
```json
{{
  "subject": "Inquiry regarding Data Scientist role at TechCorp",
  "body": "Hi [Contact Name],\\n\\nI recently read your insightful post on LinkedIn about the challenges of deploying LLMs at scale, and it perfectly captured the complexities I've been passionate about solving. I'm writing today to express my enthusiastic interest in the Data Scientist position at TechCorp.\\n\\nIn my recent project, I led the development of an AI-powered recommendation engine, where I engineered a RAG architecture that improved retrieval precision by 40%. This experience, combined with my background in building and deploying scalable systems on GCP, seems to align directly with the needs you've outlined for this role, particularly around MLOps and model optimization.\\n\\nI am confident that my problem-solving approach and technical skills would allow me to contribute significantly to your team. Would you be open to a brief 15-minute chat next week to discuss this further?\\n\\nBest regards,\\n[Candidate Name]"
}}
```
"""
    if model_provider == "chatgpt":
        generated_content_str = call_openrouter_api(prompt, is_json_output=True)
    else: # Default to gemini
        generated_content_str = call_gemini_api(prompt, is_json_output=True)
    
    cleaned_str = generated_content_str.replace("```json", "").replace("```", "").strip()
    
    try:
        json.loads(cleaned_str)
        return cleaned_str
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from LLM response: {e}")
        print(f"LLM Response was:\n{cleaned_str}")
        raise HTTPException(status_code=500, detail="Failed to get valid JSON from the email generation agent.")

def agent_cover_letter_generator(resume_yaml: str, jd_text: str, additional_details: str, model_provider: str = "gemini") -> str:
    """
    The Cover Letter Agent. It receives a finalized resume, job description, and user notes
    to generate a tailored cover letter.
    """
    prompt = f"""
You are an expert career coach and professional writer, specializing in creating impactful cover letters that get noticed. Your task is to write a compelling, tailored cover letter based on the provided information.

**Your Goal:**
Draft a cover letter that tells a persuasive story, connecting the candidate's achievements directly to the needs outlined in the job description. The tone should be professional, confident, and genuinely enthusiastic.

**Input Information:**
1.  **Candidate's Finalized Resume (YAML format):**
    ```yaml
    {resume_yaml}
    ```
2.  **Target Job Description:**
    ---
    {jd_text}
    ---
3.  **Additional Details & Instructions from User:**
    ---
    {additional_details if additional_details else "None"}
    ---

**Your Task & Strict Instructions:**

1.  **Analyze and Synthesize:**
    - Thoroughly review the job description to identify the top 3-4 most critical requirements, challenges, and desired qualifications.
    - Scrutinize the candidate's resume to find the most relevant experiences, projects, and skills that directly address these requirements.

2.  **Draft the Cover Letter Body:**
    - **Salutation:** Begin with "Dear Hiring Committee,".
    - **Opening Paragraph:** Immediately grab the reader's attention. State the specific role you are applying for. Briefly introduce the candidate and express genuine excitement about the opportunity, perhaps mentioning something specific about the company that resonates.
    - **Body Paragraphs (2-3 paragraphs):** This is the core of the letter.
        - **Create a Narrative:** Do not simply list skills from the resume. Instead, build a story. Select 2-3 of the most powerful examples (from experience or projects) that align with the job's needs.
        - **Show, Don't Tell:** For each example, briefly describe the challenge or problem, the specific action the candidate took, and the positive, quantifiable outcome. Use the resume as a source of facts but elaborate on the *impact*.
        - **Connect to the JD:** Explicitly tie these stories back to the requirements of the job description. For example: "My work in developing a scalable ETL pipeline, which reduced data processing latency by 30%, has prepared me to tackle the data engineering challenges you've outlined."
        - **Incorporate User Notes:** Seamlessly weave in any points from the "Additional Details" to further personalize the letter.
    - **Closing Paragraph:** Reiterate your strong interest in the role and the company. Confidently state how your skills will benefit the team. Include a clear call to action, such as "I am eager to discuss how my background in data science and machine learning can contribute to your team's success."

3.  **Formatting:**
    - The entire output should be a single JSON object.
    - The JSON object must contain one key: `cover_letter_body`.
    - The value should be a single string containing the entire body of the cover letter, from the salutation to the final paragraph. Use `\\n\\n` for paragraph breaks.
    - **DO NOT** include the sign-off (e.g., "Yours sincerely,"), the candidate's name, or contact details. This will be appended programmatically.

**Example Output:**
```json
{{
  "cover_letter_body": "Dear Hiring Committee,\\n\\nI am writing to express my enthusiastic interest in the Data Scientist position at TechCorp, as advertised on LinkedIn. Having followed TechCorp's innovations in machine learning, I am particularly impressed by your commitment to developing scalable AI solutions, and I am confident that my skills and experience align perfectly with the requirements of this role.\\n\\nIn my previous role at AB InBev, I led a project to automate financial reporting workflows, which involved designing and deploying robust ETL pipelines that ultimately saved the company $500,000 annually. This experience directly relates to your need for a candidate who can handle large-scale data systems and deliver measurable business impact. Furthermore, my work on the AI Fantasy Team Predictor project honed my skills in model tuning and MLOps, where I improved prediction accuracy by over 95% and deployed the system on a scalable GCP architecture—capabilities that I am excited to bring to your team.\\n\\nMy background has equipped me with a strong foundation in both the theoretical and practical aspects of data science. I am eager to discuss how my problem-solving abilities and technical expertise can help TechCorp continue to innovate. Thank you for your time and consideration.\\n\\nI look forward to hearing from you soon."
}}
```
"""
    if model_provider == "chatgpt":
        generated_content_str = call_openrouter_api(prompt, is_json_output=True)
    else: # Default to gemini
        generated_content_str = call_gemini_api(prompt, is_json_output=True)
    
    cleaned_str = generated_content_str.replace("```json", "").replace("```", "").strip()
    
    try:
        json.loads(cleaned_str)
        return cleaned_str
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from LLM response: {e}")
        print(f"LLM Response was:\n{cleaned_str}")
        raise HTTPException(status_code=500, detail="Failed to get valid JSON from the cover letter generation agent.")