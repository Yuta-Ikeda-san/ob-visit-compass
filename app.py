import os
import json
import re
from datetime import datetime
from flask import Flask, render_template, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")

client = InferenceClient(token=os.getenv("HF_API_TOKEN"))
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class ConsultSession(db.Model):
    __tablename__ = "consult_sessions"
    id = db.Column(db.Integer, primary_key=True)
    industry = db.Column(db.String(100))
    job_type = db.Column(db.String(100))
    user_message = db.Column(db.Text)
    agent_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def clean_response(content):
    if "<think>" in content and "</think>" in content:
        content = content.split("</think>")[-1].strip()
    return content


def call_llm(prompt):
    response = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_NAME,
        max_tokens=1500
    )
    return clean_response(response.choices[0].message.content)


def generate_question_list(industry, job_type, user_message):
    extra_context = f"\n学生の相談内容: {user_message}" if user_message else ""
    prompt = f"""あなたは就活生のOB訪問を支援するAgentです。
業界: {industry}
職種: {job_type}{extra_context}

上記の情報を踏まえて、この業界・職種のOB訪問で聞くべき質問を5つ、
学生が実際に使える形で日本語で提案してください。
学生の相談内容がある場合は、その内容を反映した質問にしてください。
番号付きリストで出力してください。

重要な出力ルール:
- ユーザーにそのまま送る返答のみを出力してください
- 質問リストの前後に解説や補足説明を追加しないでください"""
    return call_llm(prompt)


def ask_for_missing_info(state, user_message):
    prompt = f"""あなたは就活生のOB訪問を支援するAgentです。
これまでの会話で分かっている情報:
業界: {state.get('industry') or '不明'}
職種: {state.get('job_type') or '不明'}
ユーザーの最新の発言: {user_message}

まだ業界か職種の情報が不足しています。
不足している情報を1つだけ、丁寧に聞き返してください。
すでに分かっている情報は聞き直さないでください。

重要な出力ルール:
- ユーザーにそのまま送る返答の文章だけを出力してください
- 解説、理由、分析、箇条書きのまとめなどは一切含めないでください
- Markdown記法（**や見出しなど）は使わないでください
- 出力は2〜3文程度の短い日本語の会話文のみにしてください"""
    return call_llm(prompt)


def extract_info(state, user_message):
    """ユーザーの発言から業界・職種らしき情報を抽出してstateに反映する"""
    prompt = f"""あなたは就活生の発言から情報を抽出するアシスタントです。

現在分かっている情報:
業界: {state.get('industry') or '(まだ不明)'}
職種: {state.get('job_type') or '(まだ不明)'}

ユーザーの最新の発言: 「{user_message}」

上記のユーザー発言と、これまでの情報を組み合わせて、
最新の「業界」と「職種」を判定してください。
発言に新しい情報がなければ、既存の情報をそのまま使ってください。
分からない項目は空文字("")にしてください。

出力は必ず以下のJSON形式のみにしてください。前置きや説明文は一切書かないでください:
{{"industry": "業界名", "job_type": "職種名"}}"""

    result = call_llm(prompt)
    match = re.search(r'\{.*\}', result, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if data.get("industry"):
                state["industry"] = data["industry"]
            if data.get("job_type"):
                state["job_type"] = data["job_type"]
        except json.JSONDecodeError:
            pass
    return state


@app.route("/")
def index():
    session.clear()
    session["chat_log"] = []
    session["state"] = {"industry": "", "job_type": ""}
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.form.get("message", "").strip()
    if "chat_log" not in session:
        session["chat_log"] = []
        session["state"] = {"industry": "", "job_type": ""}

    chat_log = session["chat_log"]
    state = session["state"]

    chat_log.append({"role": "user", "content": user_message})

    state = extract_info(state, user_message)

    if not state.get("industry") or not state.get("job_type"):
        agent_reply = ask_for_missing_info(state, user_message)
    else:
        agent_reply = generate_question_list(state["industry"], state["job_type"], user_message)

        record = ConsultSession(
            industry=state["industry"],
            job_type=state["job_type"],
            user_message=user_message,
            agent_response=agent_reply
        )
        db.session.add(record)
        db.session.commit()

    chat_log.append({"role": "agent", "content": agent_reply})

    session["chat_log"] = chat_log
    session["state"] = state
    session.modified = True

    return jsonify({"reply": agent_reply, "chat_log": chat_log})


@app.route("/history")
def history():
    records = ConsultSession.query.order_by(ConsultSession.created_at.desc()).all()
    return render_template("history.html", records=records)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)