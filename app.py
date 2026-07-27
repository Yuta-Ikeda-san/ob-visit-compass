import os
from datetime import datetime
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

app = Flask(__name__)
client = InferenceClient(token=os.getenv("HF_API_TOKEN"))

# Hugging Face 無料インファレンスAPIで安定して動作する高性能モデル
MODEL_NAME = "Qwen/Qwen2.5-72B-Instruct"

# PostgreSQL接続URIの調整（DATABASE_URLが空の場合はローカルのSQLiteを使用するようフォールバックを設定）
db_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Render等のクラウドDBタイムアウト（OperationalError）対策
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,  # DB操作前に接続状態を確認し、切断されていれば自動で再接続
    "pool_recycle": 300,    # 5分（300秒）ごとに接続を張り直す
}

db = SQLAlchemy(app)


class ConsultSession(db.Model):
    __tablename__ = "consult_sessions"
    id = db.Column(db.Integer, primary_key=True)
    industry = db.Column(db.String(100))
    job_type = db.Column(db.String(100))
    user_message = db.Column(db.Text)
    agent_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def ask_agent(industry, job_type, user_message):
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
    return content


# データベースのテーブルを作成
with app.app_context():
    db.create_all()


# メインページ（フォーム送信・回答表示）
@app.route("/", methods=["GET", "POST"])
def index():
    agent_response = ""
    if request.method == "POST":
        industry = request.form.get("industry")
        job_type = request.form.get("job_type")
        user_message = request.form.get("user_message")

        # 1. LLMからの回答を取得
        agent_response = ask_agent(industry, job_type, user_message)

        # 2. 回答取得後にDBへ保存
        try:
            session_record = ConsultSession(
                industry=industry,
                job_type=job_type,
                user_message=user_message,
                agent_response=agent_response
            )
            db.session.add(session_record)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"DB Save Error: {e}")

    return render_template("index.html", result=agent_response)


# 履歴表示ページ
@app.route("/history")
def history():
    sessions = ConsultSession.query.order_by(ConsultSession.created_at.desc()).all()
    # history.html 側の {% for record in records %} に合わせて records= で渡す
    return render_template("history.html", records=sessions)


if __name__ == "__main__":
    app.run(debug=True)