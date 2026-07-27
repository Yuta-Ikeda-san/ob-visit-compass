import os
from flask import Flask, render_template, request
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

app = Flask(__name__)
client = InferenceClient(token=os.getenv("HF_API_TOKEN"))

MODEL_NAME = "deepseek-ai/DeepSeek-R1"

def ask_agent(industry, job_type, user_message, history):
    if not industry or not job_type:
        prompt = f"""あなたは就活生のOB訪問を支援するAgentです。
ユーザーの発言: {user_message}
まだ業界か職種の情報が不足しています。
不足している情報を1つだけ、丁寧に聞き返してください。"""
    else:
        extra_context = f"\n学生の相談内容: {user_message}" if user_message else ""
        prompt = f"""あなたは就活生のOB訪問を支援するAgentです。
業界: {industry}
職種: {job_type}{extra_context}

上記の情報を踏まえて、この業界・職種のOB訪問で聞くべき質問を5つ、
学生が実際に使える形で日本語で提案してください。
学生の相談内容がある場合は、その内容を反映した質問にしてください。
番号付きリストで出力してください。"""

    response = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_NAME,
        max_tokens=1500
    )

    content = response.choices[0].message.content

    if "<think>" in content and "</think>" in content:
        content = content.split("</think>")[-1].strip()

    return content


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        industry = request.form.get("industry", "").strip()
        job_type = request.form.get("job_type", "").strip()
        user_message = request.form.get("user_message", "").strip()

        result = ask_agent(industry, job_type, user_message, history=None)

    return render_template("index.html", result=result)


if __name__ == "__main__":
    app.run(debug=True)