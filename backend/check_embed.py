import os
from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
result = genai.embed_content(
    model="models/gemini-embedding-001",
    content="test sentence",
    task_type="retrieval_document",
    output_dimensionality=768,
)
print("length:", len(result["embedding"]))