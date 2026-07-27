import os
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from huggingface_hub import InferenceClient

app = Flask(__name__)

# --- データベース設定 ---
db_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Hugging Face APIトークン
hf_token = os.environ.get("HF_API_TOKEN")

# ★ 最も安定・高速に動作するモデルのリストに刷新 ★
MODEL_LIST = [
    "meta-llama/Llama-3.2-3B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct"
]

# --- データベースモデル ---
class SessionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    industry = db.Column(db.String(100), nullable=True)
    job_type = db.Column(db.String(100), nullable=True)
    user_message = db.Column(db.Text, nullable=True)
    agent_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone(timedelta(hours=9))))

# DBのテーブル作成
with app.app_context():
    db.create_all()

# --- ルーティング ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.form.get("message", "").strip()
    if not user_msg:
        return jsonify({"reply": "メッセージを入力してください。"})

    system_prompt = (
        "あなたは就活生のOB訪問をサポートするプロのアシスタント「OB訪問コンパス」です。"
        "ユーザーから業界・職種や相談内容を受け取り、OB訪問で質問すべき具体的な質問リストとアドバイスを分かりやすく丁寧な日本語で生成してください。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg}
    ]

    bot_reply = None

    # モデルを順番に試すリトライ処理
    for model_name in MODEL_LIST:
        try:
            print(f"Trying model: {model_name}...")
            client = InferenceClient(model_name, token=hf_token, timeout=15)
            response = client.chat_completion(
                messages=messages,
                max_tokens=800,
                temperature=0.7
            )
            bot_reply = response.choices[0].message.content
            if bot_reply:
                print(f"Success with model: {model_name}")
                break
        except Exception as e:
            print(f"Failed with {model_name}: {e}")
            time.sleep(0.5)

    # すべてのモデルで失敗した場合のフォールバック
    if not bot_reply:
        bot_reply = "申し訳ありません。AIサーバーが一時的に混雑しています。もう一度送信してみてください。"

    # DBに相談ログを保存
    try:
        new_log = SessionLog(
            industry="就活相談",
            job_type="指定なし",
            user_message=user_msg,
            agent_response=bot_reply
        )
        db.session.add(new_log)
        db.session.commit()
    except Exception as e:
        print("DB Save Error:", e)

    return jsonify({"reply": bot_reply})

@app.route("/history")
def history():
    sessions = SessionLog.query.order_by(SessionLog.created_at.desc()).all()
    return render_template("history.html", records=sessions)

# ★ 1件削除機能 ★
@app.route("/delete/<int:record_id>", methods=["POST"])
def delete_record(record_id):
    record = SessionLog.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    return redirect(url_for("history"))

# ★ 全件削除機能 ★
@app.route("/delete_all", methods=["POST"])
def delete_all_records():
    SessionLog.query.delete()
    db.session.commit()
    return redirect(url_for("history"))

if __name__ == "__main__":
    app.run(debug=True)