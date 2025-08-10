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
    - Write a powerful, 1-line professional summary (max 20 words, make the entire line is 140 characters strictly.) that perfectly mirrors the top requirements of the job description, optimized for ATS keyword matching. My experience is 3 years.

2.  **`skills_reordered`**:
    - **Reorder the skill category blocks** from the fixed information based on their relevance to the job description.
    - **Reorder the individual skills within each category** to prioritize those most relevant to the job description first.
    - **Identify skills mentioned in the job description that are missing** from the candidate's list but are relevant to their profile. Make sure you are not repeating skills acorss the categories as well.
    - **Insert these new, relevant skills into the most appropriate existing categories**, maintaining the relevance-based order. Do NOT create new categories.

3.  **`experience_bullets`**:
    - All the content should heavily be dependent on the job description. Use less of context from YAML and more job description focused.
    - Incoorporate the industry if mentioned in the job description. Ex: if finance is mentioned, invent saying financial data or financial reports.
    - This is your most critical task. You must generate bullet points using the **Problem-Action-Result (PAR)** framework. do it for majority of the bullet points. Just optimise for ATS.
    - For majority bullets, you must first articulate the business **problem** or **challenge**, then the **action** taken, and finally the **quantifiable result**.
    - **INVENT ACTION POINTS**: From the context provided understand the intent of the work and extrapolate / invent action points highly based on the job description. Do NOT just rephrase the existing points. 
    - **INVENT QUANTIFIABLE METRICS.** For majority bullets **MUST** include a plausible, impactful metric. Invent realistic ones if not provided. Examples: "reduced latency by 30%", "processed 500GB of data", "increased user engagement by 15%", "saved $50,000 in operational costs".
    - Word Count: make the entire line is 140 characters. strict.
    - **Strategic Bolding**: Identify the most critical parts of each bullet points based on the bullet itself and the job description. Wrap these keywords in `<b>...</b>` tags. Use this sparingly—aim for 1-3 bolded phrases per bullet to maximize impact without cluttering the text.
    - Number of Bullets:
        - DRINKS: 4 points
        - AB INBEV: 8 points
        - Janta Ka Mood: 2 points

4.  **`projects_reordered`**:
    - Reorder projects based on job relevance.
    - All the content should heavily be dependent on the job description. Use less of context from YAML and more job description focused.
    - Incoorporate the industry if mentioned in the job description. Ex: if finance is mentioned, invent saying financial data or financial reports.
    - This is your most critical task. You must generate bullet points using the **Problem-Action-Result (PAR)** framework. do it for majority of the bullet points. Just optimise for ATS.
    - For majority bullets, you must first articulate the business **problem** or **challenge**, then the **action** taken, and finally the **quantifiable result**.
    - **INVENT ACTION POINTS**: From the context provided understand the intent of the work and extrapolate / invent action points highly based on the job description. Do NOT just rephrase the existing points. 
    - **INVENT QUANTIFIABLE METRICS.** For majority bullets **MUST** include a plausible, impactful metric. Invent realistic ones if not provided. Examples: "reduced latency by 30%", "processed 500GB of data", "increased user engagement by 15%", "saved $50,000 in operational costs".
    - Word Count: make the entire line is 140 characters. strict.
    - **Strategic Bolding**: Identify the most critical parts of each bullet points based on the bullet itself and the job description. Wrap these keywords in `<b>...</b>` tags. Use this sparingly—aim for 1-3 bolded phrases per bullet to maximize impact without cluttering the text.
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