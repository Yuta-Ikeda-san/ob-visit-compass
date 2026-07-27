\# システムアーキテクチャ



\## Web 3層構成



```mermaid

graph TD

&#x20;   A\[ユーザー ブラウザ] -->|HTTPS| B\[Web層 Render Web Service]

&#x20;   B -->|Flask アプリケーション| C\[Application層 Agentロジック]

&#x20;   C -->|SQL| D\[DB層 PostgreSQL]

&#x20;   C -->|API呼び出し| E\[Hugging Face Inference API]

```



\## 非機能要件



\### RPO/RTO

\- RPO（目標復旧時点）：24時間（1日1回のDBバックアップを想定）

\- RTO（目標復旧時間）：4時間以内（Renderの再デプロイで復旧可能な構成）



\### DR（バックアップ）

\- Render標準のPostgreSQLバックアップ機能を利用

\- 週次で手動エクスポート（pg\_dump）も実施し、ローカルに保管



\### Performance

\- 想定同時アクセス数：10人程度（授業内デモ利用を想定した小規模構成）

\- LLM応答時間：Hugging Face無料枠のため数秒〜数十秒のレイテンシを許容

\- ボトルネック：LLM API呼び出しの応答速度（Agentのステップが増えるほど遅延）

