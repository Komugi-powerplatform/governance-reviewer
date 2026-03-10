# Governance Reviewer - ガバナンス審査自動化ツール

社内規程・ポリシー文書をAIで自動レビューするOSSツール。あらかじめ定義された審査観点に基づいてPDFを構造化・AI解析し、チェック結果をレポート出力する。

**本業に専念したい人の「面倒ごと」を解決する。** 規程改訂のたびに目視で全項目をチェックする作業を、AIに任せて数分で終わらせる。

## 特徴

- **5つの入力形式** -- デフォルト / YAML・JSON / Excel・CSV / PDF / テキスト
- **LLM切り替え可能** -- Claude / OpenAI / ローカルモデルを litellm 経由で統一的に利用
- **セルフホスト対応** -- 機密文書を外部に送らずオンプレミスで運用可能
- **デフォルト審査観点27項目同梱** -- 情報セキュリティ、個人情報保護、コンプライアンス、BCP、文書管理、委託先管理
- **Gradio UI** -- 非エンジニアでもブラウザから操作可能
- **Hugging Face Spaces対応** -- 無料で公開・共有可能

## スクリーンショット

> TODO: 後日追加予定

## クイックスタート

```bash
git clone https://github.com/your-org/governance-reviewer.git
cd governance-reviewer
pip install -r requirements.txt

# いずれかのAPIキーを設定
export ANTHROPIC_API_KEY="your-key"
# または
export OPENAI_API_KEY="your-key"

python3 app.py
# → http://localhost:7860 でUIが起動
```

## 使い方

| ステップ | タブ | 操作 |
|----------|------|------|
| 1 | 審査観点の設定 | デフォルト27項目をロード、またはYAML/JSON/Excel/CSV/PDF/テキストで独自観点をアップロード |
| 2 | 審査実行 | 審査対象のPDFをアップロードして「審査開始」 |
| 3 | 結果・レポート | 判定結果の一覧を確認し、Markdown/HTMLレポートをダウンロード |

### 判定ラベル

| ラベル | 意味 |
|--------|------|
| 適合 | 審査観点を満たしている |
| 要確認 | 一部不明確、または追加確認が必要 |
| 不適合 | 審査観点を満たしていない |
| 該当なし | 対象文書の範囲外 |

## 審査観点の入力形式

### デフォルト（大企業ガバナンス共通27項目）

ISMS (ISO 27001)、個人情報保護法、J-SOX、BCPガイドライン等を参考に構成した汎用的な審査観点セット。ボタン1つでロードできる。

### YAML / JSON

```yaml
criteria:
  - id: C001
    category: "情報セキュリティ"
    name: "パスワードポリシーの明記"
    description: "パスワードの長さ、複雑性、変更頻度に関する規定があるか"
    severity: "high"
  - id: C002
    category: "情報セキュリティ"
    name: "アクセス制御と権限管理"
    description: "最小権限の原則に基づくアクセス制御が整備されているか"
    severity: "high"
```

### Excel / CSV

以下のカラムを含むファイルを用意する。カラム名は英語・日本語いずれでも認識する。

| id | カテゴリ (category) | 観点名 (name) | 説明 (description) | 重要度 (severity) |
|----|---------------------|---------------|---------------------|-------------------|
| C001 | 情報セキュリティ | パスワードポリシーの明記 | パスワードの長さ、複雑性... | high |

### PDF / テキスト

既存の審査基準書PDFやテキストをアップロードすると、LLMが自動的に構造化された審査観点リストに変換する。

## プロジェクト構成

```
governance-reviewer/
├── app.py                              # Gradio UIエントリポイント
├── config.py                           # モデル・パラメータ設定
├── requirements.txt
├── analysis/
│   ├── engine.py                       # 審査実行エンジン
│   ├── llm_client.py                   # litellm経由のLLMクライアント
│   └── prompts.py                      # プロンプトテンプレート
├── criteria/
│   ├── loader.py                       # 審査観点の統一ローダー
│   ├── parser_structured.py            # YAML/JSON/CSV/Excelパーサー
│   ├── parser_pdf.py                   # PDF→審査観点のAI抽出
│   └── defaults/
│       └── corporate_governance.yaml   # デフォルト27項目
├── document/
│   ├── extractor.py                    # PDF→テキスト抽出
│   └── chunker.py                      # セクション分割・チャンキング
├── report/
│   ├── generator.py                    # Markdown/HTMLレポート生成
│   └── templates/
│       └── review_report.html          # HTMLレポートテンプレート
└── examples/                           # サンプルファイル
```

## 設定

### 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `ANTHROPIC_API_KEY` | Anthropic APIキー（Claude利用時） | -- |
| `OPENAI_API_KEY` | OpenAI APIキー（GPT利用時） | -- |
| `GOVERNANCE_LLM_MODEL` | 使用するLLMモデル名 | `claude-sonnet-4-20250514` |

### 対応モデル

UI上のドロップダウンから選択可能。litellm経由のため、litellmが対応する任意のモデルを `config.py` に追加して利用できる。

| モデル | プロバイダ |
|--------|-----------|
| `claude-sonnet-4-20250514` | Anthropic |
| `claude-haiku-4-5-20251001` | Anthropic |
| `gpt-4o` | OpenAI |
| `gpt-4o-mini` | OpenAI |

### チューニングパラメータ

`config.py` で以下を調整可能。

| パラメータ | 説明 | デフォルト |
|-----------|------|-----------|
| `MAX_CHUNK_TOKENS` | PDF分割時の最大チャンクトークン数 | 8000 |
| `CHUNK_OVERLAP_TOKENS` | チャンク間のオーバーラップトークン数 | 500 |

## ライセンス

MIT

## Contributing

PRを歓迎します。バグ報告・機能提案はIssueからどうぞ。
