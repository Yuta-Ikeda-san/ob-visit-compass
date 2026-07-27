import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

client = InferenceClient(token=os.getenv("HF_API_TOKEN"))

response = client.chat_completion(
    messages=[{"role": "user", "content": "こんにちは、自己紹介してください"}],
    model="deepseek-ai/DeepSeek-R1",
    max_tokens=200
)

print(response.choices[0].message.content)