# OB訪問コンパス（OB Visit Compass）

就活生がOB訪問の準備をサポートするAI Agentアプリケーションです。
業界・職種を対話形式で聞き取り、Hugging Face経由のLLM（Qwen2.5-72B-Instruct）が
状況を判断しながら、OB訪問で使える具体的な質問リストを生成します。

## デプロイURL
https://ob-visit-compass.onrender.com

（Render無料プランのため、しばらくアクセスがないとスリープします。
初回アクセス時は起動に30秒〜1分程度かかる場合があります）

## 主な機能

- チャット形式での対話によるアシスタント機能（業界・職種や悩みを自然な会話でヒアリング）
- OB訪問で使える具体的な質問リストとアドバイスの自動生成
- 相談履歴のデータベース保存・一覧表示（アコーディオン表示対応）
- 履歴の管理機能（個別削除・一括削除）
- 3カラムレスポンシブUI（特長紹介・おすすめ相談例のガイドパネル付き）

## ドキュメント

- ペルソナ・Motivation Graph・Story Board：`docs/persona.md`
- システムアーキテクチャ・非機能要件：`docs/architecture.md`

## 技術構成

- Flask（Webフレームワーク）
- Flask-SQLAlchemy（ORM）
- PostgreSQL（Render上に構築）/ SQLite（ローカル開発用）
- Hugging Face Inference API（複数モデルのフォールバック方式：Qwen2.5-7B-Instruct, Llama-3.2-3B-Instruct, Mistral-7B-Instruct-v0.3, Qwen2.5-72B-Instructの順に試行し、安定性を確保）
- Render（デプロイ・ホスティング）
- Gunicorn（本番用WSGIサーバー）

## 開発プロセス

Claude Codeを用いたAIエージェント駆動開発（Vibe Coding）で構築しました。
GitHub Projects（Kanban）で進捗を管理し、PM・Business Analyst・Architect・
Infra Engineer・AI Engineerの役割を一人で担当しました。

## AIモデルチューニングの記録

開発の過程で、以下の試行錯誤を経てレスポンス品質と安定性を改善しました。

### 1. プロンプト設計の改善
当初、業界・職種のみでプロンプトを構成していたが、ユーザーの相談内容
（`user_message`）が生成結果に反映されない問題があった。プロンプトに
相談内容を明示的に組み込むことで、パーソナライズされた質問リストを
生成できるよう改善した。

### 2. 使用モデルの変更（DeepSeek-R1 → Qwen2.5-72B-Instruct）
初期はDeepSeek-R1を使用していたが、以下の問題が発生した。
- 推論の思考過程（`<think>`タグ）がそのままレスポンスに含まれてしまう
- 推論に時間がかかり、Render本番環境でGunicornのタイムアウト
  （デフォルト30秒）を超えて`Internal Server Error`が発生する

対策として、より高速かつ高品質に応答する大型モデル「Qwen2.5-72B-Instruct」へ
モデルを変更した。これにより、応答速度と生成テキストの精度が大きく改善した。

### 3. 出力形式の厳格化
モデルが「返答内容」と「なぜそう答えたかの解説」を混在させて出力する
問題があった。プロンプトに「解説や分析は含めず、ユーザーに送る会話文
のみを出力する」という制約を明示的に追加することで解消した。

### 4. 本番環境でのタイムアウト対応
Render環境では、モデル変更後も一部のケースでタイムアウトが発生した
ため、`Procfile`に`--timeout 120`を追加し、Gunicornのタイムアウトを
延長することで安定動作を実現した。

## 今後の改善案

- RAGによる実際の業界研究資料の組み込み
- Graph RAG（Neo4j等）を用いた、より構造的な業界知識の活用
- OB訪問前チェックリストなど、周辺機能の追加