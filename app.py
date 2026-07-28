import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from huggingface_hub import InferenceClient

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# --- データベース設定 ---
db_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Hugging Face APIトークン
hf_token = os.environ.get("HF_API_TOKEN")

# 安定・高速に動作するモデルのフォールバックリスト
MODEL_LIST = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
]
JST = timezone(timedelta(hours=9))


def now_jst():
    return datetime.now(JST)


# --- データベースモデル ---
class SessionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    industry = db.Column(db.String(100), nullable=True)
    job_type = db.Column(db.String(100), nullable=True)
    user_message = db.Column(db.Text, nullable=True)
    agent_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=now_jst)


with app.app_context():
    db.create_all()


def call_llm(prompt):
    """複数モデルを順番に試すフォールバック付きLLM呼び出し"""
    messages = [{"role": "user", "content": prompt}]
    for model_name in MODEL_LIST:
        try:
            print(f"Trying model: {model_name}...")
            client = InferenceClient(model_name, token=hf_token, timeout=30)
            response = client.chat_completion(
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            content = response.choices[0].message.content
            if content:
                print(f"Success with model: {model_name}")
                return clean_response(content)
        except Exception as e:
            print(f"Failed with {model_name}: {e}")
            time.sleep(0.5)
    return "申し訳ありません。AIサーバーが一時的に混雑しています。もう一度送信してみてください。"


def clean_response(content):
    if "<think>" in content and "</think>" in content:
        content = content.split("</think>")[-1].strip()
    return content


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
- 質問リストの前後に解説や補足説明を追加しないでください
- 必ず日本語のみで出力してください"""
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
- 出力は2〜3文程度の短い日本語の会話文のみにしてください
- 必ず日本語のみで出力してください"""
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
業界名・職種名は必ず日本語で出力してください。

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


# --- ルーティング ---

@app.route("/")
def index():
    session.clear()
    session["state"] = {"industry": "", "job_type": ""}
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.form.get("message", "").strip()
    if not user_msg:
        return jsonify({"reply": "メッセージを入力してください。"})

    if "state" not in session:
        session["state"] = {"industry": "", "job_type": ""}

    state = session["state"]
    state = extract_info(state, user_msg)

    if not state.get("industry") or not state.get("job_type"):
        bot_reply = ask_for_missing_info(state, user_msg)
    else:
        bot_reply = generate_question_list(state["industry"], state["job_type"], user_msg)

        try:
            new_log = SessionLog(
                industry=state["industry"],
                job_type=state["job_type"],
                user_message=user_msg,
                agent_response=bot_reply
            )
            db.session.add(new_log)
            db.session.commit()
        except Exception as e:
            print("DB Save Error:", e)

    session["state"] = state
    session.modified = True

    return jsonify({"reply": bot_reply})


@app.route("/history")
def history():
    sessions = SessionLog.query.order_by(SessionLog.created_at.desc()).all()
    return render_template("history.html", records=sessions)


@app.route("/delete/<int:record_id>", methods=["POST"])
def delete_record(record_id):
    record = SessionLog.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    return redirect(url_for("history"))


@app.route("/delete_all", methods=["POST"])
def delete_all_records():
    SessionLog.query.delete()
    db.session.commit()
    return redirect(url_for("history"))


if __name__ == "__main__":
    app.run(debug=True)