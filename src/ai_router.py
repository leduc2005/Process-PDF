"""
ai_router.py (Đã nâng cấp Exponential Backoff & Chống Rate Limit 429)
"""
import os, json, base64, time, re, litellm
from dotenv import load_dotenv
from pathlib import Path

_env_path = Path(__file__).parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(_env_path, override=True)

os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY", "")

TEXT_MODEL = "gemini/gemini-3.5-flash-lite"
VISION_MODEL = "gemini/gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 8192
MAX_RETRIES = 3

SUMMARY_PROMPT = """You are an educational expert. Summarize the following content into a short Micro-learning lecture (3-5 key points).
CRITICAL INSTRUCTIONS:
- You MUST answer in the EXACT SAME LANGUAGE as the source content.
- FOR MATH/PHYSICS EXERCISES WITHOUT PROVIDED SOLUTIONS: DO NOT attempt to calculate or solve the numerical problems yourself. Instead, create questions that test theory, formulas, or the method of solving.
- If there are math formulas, describe them in words. DO NOT use backslash (\) character in JSON.
- Output MUST be valid JSON.

Content to summarize:
{content}

Return JSON in this format:
{{
  "title": "Course Title",
  "summary_points": ["Point 1", "Point 2", "Point 3"],
  "key_concepts": ["concept 1", "concept 2"]
}}"""

QUIZ_PROMPT = """You are a quiz creation expert. Based on the content, create {num_questions} multiple-choice questions.
CRITICAL INSTRUCTIONS:
- You MUST write the questions and options in the EXACT SAME LANGUAGE as the source content.
- Each question has 4 options (A, B, C, D) and only 1 correct answer.
- FOR MATH/PHYSICS EXERCISES WITHOUT PROVIDED SOLUTIONS: DO NOT attempt to calculate or solve the numerical problems yourself. Instead, create questions that test theory, formulas, or the method of solving.
- If there are math formulas, describe them in words. DO NOT use backslash (\) character in JSON.
- Output MUST be valid JSON.

Content:
{content}

Return JSON in this format:
{{
  "questions": [
    {{
      "question": "Question text?",
      "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}},
      "correct_answer": "A",
      "explanation": "Short explanation"
    }}
  ]
}}"""

VISION_PROMPT = """You are an educational expert. Analyze the visual elements in this page.
CRITICAL INSTRUCTIONS:
- You MUST answer in the EXACT SAME LANGUAGE as the text inside the image.
- Do NOT use backslash (\) character in JSON.
Return JSON in this format:
{{
  "page_description": "Detailed description...",
  "key_points": ["Point 1", "Point 2"],
  "visual_elements": ["Chart 1", "Diagram 2"]
}}"""

def _parse_json_response(response_text: str) -> dict:
    text = response_text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    try: return json.loads(text.strip())
    except: return {"raw_text": response_text, "parse_error": True}

# --- VŨ KHÍ 1: EXPONENTIAL BACKOFF & SMART RATE LIMIT HANDLING ---
def safe_litellm_call(model, messages, max_tokens, retry_count=0):
    try:
        response = litellm.completion(model=model, messages=messages, temperature=0.3, max_tokens=max_tokens)
        return _parse_json_response(response.choices[0].message.content)
    except Exception as e:
        error_str = str(e).lower()
        if retry_count >= MAX_RETRIES:
            return {"error": f"Failed after {MAX_RETRIES} retries. Last error: {error_str[:100]}"}
        
        # Bắt lỗi 429 Rate Limit
        if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
            wait_time = 25 # Mặc định chờ 25s cho gói free 15RPM
            # Cố gắng bóc tách số giây từ câu thông báo của Google (VD: "Please retry in 20.8s")
            match = re.search(r"retry in ([\d\.]+)s", error_str)
            if match:
                wait_time = int(float(match.group(1))) + 2
            
            print(f"  [AI Router] 🚨 RATE LIMIT (429)! Google chan API. Backoff: Cho {wait_time}s... (Thu lan {retry_count+1})")
            time.sleep(wait_time)
            return safe_litellm_call(model, messages, max_tokens, retry_count + 1)
        
        # Lỗi 503 Server Quá tải tạm thời
        elif "503" in error_str or "unavailable" in error_str:
            wait_time = (2 ** retry_count) * 2  # 2s, 4s, 8s...
            print(f"  [AI Router] ⚠️ Lỗi 503 Google qua tai. Exponential Backoff: Cho {wait_time}s... (Thu lan {retry_count+1})")
            time.sleep(wait_time)
            return safe_litellm_call(model, messages, max_tokens, retry_count + 1)
            
        else:
            print(f"  [AI Router] ❌ Loi khong xac dinh: {error_str[:100]}. Cho 2s...")
            time.sleep(2)
            return safe_litellm_call(model, messages, max_tokens, retry_count + 1)

def call_text_llm(prompt: str, model: str = TEXT_MODEL, max_tokens: int = MAX_OUTPUT_TOKENS) -> dict:
    return safe_litellm_call(model, [{"role": "user", "content": prompt}], max_tokens)

def call_vision_llm(prompt: str, image_bytes: bytes, model: str = VISION_MODEL, max_tokens: int = MAX_OUTPUT_TOKENS) -> dict:
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}]}]
    return safe_litellm_call(model, messages, max_tokens)

def generate_summary(text: str, model: str = TEXT_MODEL) -> dict:
    return call_text_llm(SUMMARY_PROMPT.format(content=text[:8000]), model=model)

def generate_quiz(text: str, num_questions: int = 5, model: str = TEXT_MODEL) -> dict:
    result = call_text_llm(QUIZ_PROMPT.format(content=text[:8000], num_questions=num_questions), model=model)
    if result.get("parse_error"):
        print(f"  ⚠️ JSON parse loi! Thu lai voi 3 cau...")
        result = call_text_llm(QUIZ_PROMPT.format(content=text[:5000], num_questions=3), model=model)
    return result

def analyze_visual_page(image_bytes: bytes, model: str = VISION_MODEL) -> dict:
    return call_vision_llm(VISION_PROMPT, image_bytes, model=model)

