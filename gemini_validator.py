import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai
import json

logger = logging.getLogger('ai_legal_drafter.gemini_validator')

load_dotenv()
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file or environment variables.")

genai.configure(api_key=gemini_api_key)

model = genai.GenerativeModel("gemini-1.5-pro")


def validate_case(original_file_path, generated_pdf_path, json_output):
    logger.info('validate_case called')
    logger.debug('Original path: %s, generated path: %s', original_file_path, generated_pdf_path)
    try:
        prompt = f"""
You are a senior Supreme Court lawyer reviewing a draft legal argument.

Your job is to VALIDATE the reasoning.

You will receive:
1. Original case document
2. Generated legal arguments
3. Citations used

Tasks:

1. Check if the arguments follow logically from the document.
2. Verify whether the citations appear appropriate.
3. Identify weak arguments.
4. Identify hallucinated or suspicious citations.
5. Suggest improvements.
6. Evaluate whether the "Non-application of mind" argument is valid.

Return JSON format:

{{
"overall_validity_score":0-10,
"logic_score":0-10,
"citation_validity_score":0-10,
"issues_found":[ ],
"suggested_improvements":[ ],
"hallucinated_citations":[ ]
}}

Here is the generated case JSON:

{json.dumps(json_output)}
"""

        with open(original_file_path, "rb") as f:
            original_pdf = f.read()

        with open(generated_pdf_path, "rb") as f:
            argument_pdf = f.read()

        response = model.generate_content(
            [
                prompt,
                {"mime_type": "application/pdf", "data": original_pdf},
                {"mime_type": "application/pdf", "data": argument_pdf},
            ]
        )

        logger.info('validate_case completed successfully')
        logger.debug('Gemini response text: %s', response.text)
        return response.text
    except Exception as e:
        logger.error('validate_case failed: %s', e, exc_info=True)
        raise


    prompt = f"""
You are a senior Supreme Court lawyer reviewing a draft legal argument.

Your job is to VALIDATE the reasoning.

You will receive:
1. Original case document
2. Generated legal arguments
3. Citations used

Tasks:

1. Check if the arguments follow logically from the document.
2. Verify whether the citations appear appropriate.
3. Identify weak arguments.
4. Identify hallucinated or suspicious citations.
5. Suggest improvements.
6. Evaluate whether the "Non-application of mind" argument is valid.

Return JSON format:

{{
"overall_validity_score":0-10,
"logic_score":0-10,
"citation_validity_score":0-10,
"issues_found":[ ],
"suggested_improvements":[ ],
"hallucinated_citations":[ ]
}}

Here is the generated case JSON:

{json.dumps(json_output)}
"""

    with open(original_file_path, "rb") as f:
        original_pdf = f.read()

    with open(generated_pdf_path, "rb") as f:
        argument_pdf = f.read()

    response = model.generate_content(
        [
            prompt,
            {"mime_type": "application/pdf", "data": original_pdf},
            {"mime_type": "application/pdf", "data": argument_pdf},
        ]
    )

    return response.text