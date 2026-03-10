"""ガバナンス審査自動化アプリ - Gradio UI"""

# ---------------------------------------------------------------------------
# gradio_client の JSON schema 処理バグを修正するパッチ
# additionalProperties が bool の場合に TypeError になる問題への対処
# ---------------------------------------------------------------------------
import gradio_client.utils as _gc_utils

_original_json_schema_to_python_type = _gc_utils._json_schema_to_python_type


def _patched_json_schema_to_python_type(schema, defs=None):
    if isinstance(schema, bool):
        return "Any"
    return _original_json_schema_to_python_type(schema, defs)


_gc_utils._json_schema_to_python_type = _patched_json_schema_to_python_type

# ---------------------------------------------------------------------------

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import gradio as gr
import pandas as pd

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

import config
from criteria.loader import (
    Criterion,
    criteria_to_dataframe,
    load_defaults,
    load_from_csv,
    load_from_yaml,
)
from criteria.parser_pdf import extract_criteria_from_pdf
from criteria.parser_structured import parse_csv_excel, parse_yaml_json
from document.chunker import chunk_sections
from document.extractor import extract_and_split
from analysis.llm_client import LLMClient
from analysis.engine import run_review
from analysis.prompts import build_text_to_criteria_prompt
from report.generator import (
    generate_html_report,
    generate_markdown_report,
    generate_summary_dataframe,
)

# ---------------------------------------------------------------------------
# 状態管理
# ---------------------------------------------------------------------------
current_criteria: list[Criterion] = []


# ---------------------------------------------------------------------------
# 審査観点ロード関数群
# ---------------------------------------------------------------------------
def load_default_criteria():
    """デフォルト審査観点をロード"""
    global current_criteria
    current_criteria = load_defaults()
    df = criteria_to_dataframe(current_criteria)
    return (
        df,
        f"デフォルト審査観点をロードしました（{len(current_criteria)}項目）",
    )


def load_criteria_from_file(file, input_type: str):
    """ファイルから審査観点をロード"""
    global current_criteria

    if file is None:
        return pd.DataFrame(), "ファイルが選択されていません"

    file_path = file.name if hasattr(file, "name") else str(file)

    try:
        if input_type == "YAML / JSON":
            current_criteria = parse_yaml_json(file_path)
        elif input_type == "Excel / CSV":
            current_criteria = parse_csv_excel(file_path)
        else:
            return pd.DataFrame(), f"未対応の入力形式: {input_type}"

        df = criteria_to_dataframe(current_criteria)
        return df, f"審査観点をロードしました（{len(current_criteria)}項目）"
    except Exception as e:
        return pd.DataFrame(), f"読み込みエラー: {e}"


def load_criteria_from_pdf(file, model: str):
    """PDFから審査観点を抽出（LLM使用）"""
    global current_criteria

    if file is None:
        return pd.DataFrame(), "ファイルが選択されていません"

    file_path = file.name if hasattr(file, "name") else str(file)

    try:
        client = LLMClient(model=model)
        current_criteria = asyncio.run(extract_criteria_from_pdf(file_path, client))
        df = criteria_to_dataframe(current_criteria)
        return df, f"PDFから審査観点を抽出しました（{len(current_criteria)}項目）"
    except Exception as e:
        return pd.DataFrame(), f"抽出エラー: {e}"


def load_criteria_from_text(text: str, model: str):
    """テキスト入力から審査観点を構造化（LLM使用）"""
    global current_criteria

    if not text.strip():
        return pd.DataFrame(), "テキストが入力されていません"

    try:
        client = LLMClient(model=model)
        prompt = build_text_to_criteria_prompt(text)
        import json

        response = asyncio.run(client.complete(prompt))

        # JSON部分を抽出してパース
        response_text = response.strip()
        if "```" in response_text:
            start = response_text.find("```")
            end = response_text.rfind("```")
            if start != end:
                inner = response_text[start:end]
                first_newline = inner.find("\n")
                if first_newline != -1:
                    response_text = inner[first_newline + 1 :]

        # JSON配列またはcriteria付きオブジェクトをパース
        data = json.loads(response_text)
        if isinstance(data, dict) and "criteria" in data:
            items = data["criteria"]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]

        current_criteria = []
        for i, item in enumerate(items):
            current_criteria.append(
                Criterion(
                    id=item.get("id", f"T{i+1:03d}"),
                    category=item.get("category", "未分類"),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    severity=item.get("severity", "medium"),
                )
            )

        df = criteria_to_dataframe(current_criteria)
        return df, f"テキストから審査観点を構造化しました（{len(current_criteria)}項目）"
    except Exception as e:
        return pd.DataFrame(), f"構造化エラー: {e}"


# ---------------------------------------------------------------------------
# 審査実行
# ---------------------------------------------------------------------------
def run_governance_review(pdf_file, model):
    """審査を実行してレポートを生成"""
    global current_criteria

    if not current_criteria:
        return "", pd.DataFrame(), "審査観点がロードされていません。先にTab 1で設定してください。", None, None

    if pdf_file is None:
        return "", pd.DataFrame(), "審査対象PDFが選択されていません。", None, None

    file_path = pdf_file.name if hasattr(pdf_file, "name") else str(pdf_file)
    doc_name = Path(file_path).stem

    try:
        # PDF解析
        sections = extract_and_split(file_path)
        if not sections:
            return "", pd.DataFrame(), "PDFからテキストを抽出できませんでした。", None, None

        # チャンク分割
        chunks = chunk_sections(sections)

        # LLM審査
        client = LLMClient(model=model)

        results = asyncio.run(
            run_review(current_criteria, chunks, client)
        )

        # レポート生成
        md_report = generate_markdown_report(results, document_name=doc_name)
        html_report = generate_html_report(results, document_name=doc_name)
        summary_df = generate_summary_dataframe(results)

        # ファイル出力
        tmp_dir = tempfile.mkdtemp()
        md_path = os.path.join(tmp_dir, f"{doc_name}_審査レポート.md")
        html_path = os.path.join(tmp_dir, f"{doc_name}_審査レポート.html")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_report)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_report)

        # 統計サマリー
        stats = {}
        for r in results:
            stats[r.judgment] = stats.get(r.judgment, 0) + 1
        total = len(results)
        pass_count = stats.get("pass", 0)
        rate = (pass_count / total * 100) if total > 0 else 0

        status_msg = (
            f"審査完了: {total}項目\n"
            f"  適合: {stats.get('pass', 0)} / "
            f"要確認: {stats.get('warning', 0)} / "
            f"不適合: {stats.get('fail', 0)} / "
            f"該当なし: {stats.get('na', 0)}\n"
            f"  適合率: {rate:.1f}%"
        )

        return md_report, summary_df, status_msg, md_path, html_path

    except Exception as e:
        return "", pd.DataFrame(), f"審査実行エラー: {e}", None, None


# ---------------------------------------------------------------------------
# UI定義
# ---------------------------------------------------------------------------
def toggle_input_visibility(choice):
    """入力方法に応じてUIコンポーネントの表示を切り替え"""
    return [
        gr.update(visible=choice in ["YAML / JSON", "Excel / CSV"]),  # file_upload
        gr.update(visible=choice == "PDF（AI抽出）"),  # pdf_criteria_upload
        gr.update(visible=choice == "テキスト入力"),  # text_input
        gr.update(visible=choice in ["YAML / JSON", "Excel / CSV"]),  # load_file_btn
        gr.update(visible=choice == "PDF（AI抽出）"),  # load_pdf_btn
        gr.update(visible=choice == "テキスト入力"),  # load_text_btn
    ]


with gr.Blocks(
    title="ガバナンス審査自動化",
    theme=gr.themes.Soft(),
    css="""
    .status-box { padding: 12px; border-radius: 8px; background: #f0f4f8; }
    """,
) as app:
    gr.Markdown(
        """
        # 📋 ガバナンス審査自動化ツール
        社内規程・ポリシー文書を審査観点に基づいてAIで自動レビューします。
        """
    )

    with gr.Tabs():
        # =================================================================
        # Tab 1: 審査設定
        # =================================================================
        with gr.Tab("1. 審査観点の設定"):
            gr.Markdown("### 審査観点の入力方法を選択してください")

            with gr.Row():
                input_method = gr.Radio(
                    choices=[
                        "デフォルト（大企業ガバナンス共通）",
                        "YAML / JSON",
                        "Excel / CSV",
                        "PDF（AI抽出）",
                        "テキスト入力",
                    ],
                    value="デフォルト（大企業ガバナンス共通）",
                    label="入力方法",
                )

            # デフォルトロードボタン
            load_default_btn = gr.Button("デフォルト観点をロード", variant="primary")

            # ファイルアップロード（YAML/JSON, Excel/CSV用）
            file_upload = gr.File(
                label="審査観点ファイル（YAML / JSON / Excel / CSV）",
                file_types=[".yaml", ".yml", ".json", ".csv", ".xlsx", ".xls"],
                visible=False,
            )
            load_file_btn = gr.Button("ファイルから読み込み", visible=False)

            # PDFアップロード（AI抽出用）
            pdf_criteria_upload = gr.File(
                label="審査基準PDF",
                file_types=[".pdf"],
                visible=False,
            )
            load_pdf_btn = gr.Button("PDFから観点を抽出（AI）", visible=False)

            # テキスト入力
            text_input = gr.Textbox(
                label="審査観点（自由入力）",
                placeholder="例: セキュリティポリシーにパスワード要件が含まれているか、個人情報の取扱い規定があるか、インシデント対応手順が明記されているか",
                lines=5,
                visible=False,
            )
            load_text_btn = gr.Button("テキストから観点を構造化（AI）", visible=False)

            # LLMモデル選択（PDF抽出・テキスト構造化で使用）
            criteria_model = gr.Dropdown(
                choices=config.AVAILABLE_MODELS,
                value=config.DEFAULT_MODEL,
                label="使用モデル（AI抽出・構造化時）",
            )

            # ステータス表示
            criteria_status = gr.Textbox(
                label="ステータス", interactive=False, elem_classes=["status-box"]
            )

            # プレビュー
            criteria_preview = gr.Dataframe(
                label="審査観点プレビュー",
                headers=["ID", "カテゴリ", "観点名", "説明", "重要度"],
                interactive=False,
            )

            # イベント接続
            input_method.change(
                toggle_input_visibility,
                inputs=[input_method],
                outputs=[
                    file_upload,
                    pdf_criteria_upload,
                    text_input,
                    load_file_btn,
                    load_pdf_btn,
                    load_text_btn,
                ],
            )

            load_default_btn.click(
                load_default_criteria,
                outputs=[criteria_preview, criteria_status],
            )

            load_file_btn.click(
                load_criteria_from_file,
                inputs=[file_upload, input_method],
                outputs=[criteria_preview, criteria_status],
            )

            load_pdf_btn.click(
                load_criteria_from_pdf,
                inputs=[pdf_criteria_upload, criteria_model],
                outputs=[criteria_preview, criteria_status],
            )

            load_text_btn.click(
                load_criteria_from_text,
                inputs=[text_input, criteria_model],
                outputs=[criteria_preview, criteria_status],
            )

        # =================================================================
        # Tab 2: 審査実行
        # =================================================================
        with gr.Tab("2. 審査実行"):
            gr.Markdown("### 審査対象のPDFをアップロードして審査を実行")

            with gr.Row():
                with gr.Column(scale=2):
                    review_pdf = gr.File(
                        label="審査対象PDF",
                        file_types=[".pdf"],
                    )
                with gr.Column(scale=1):
                    review_model = gr.Dropdown(
                        choices=config.AVAILABLE_MODELS,
                        value=config.DEFAULT_MODEL,
                        label="使用モデル",
                    )
                    run_btn = gr.Button("🔍 審査開始", variant="primary", size="lg")

            review_status = gr.Textbox(
                label="審査ステータス",
                interactive=False,
                elem_classes=["status-box"],
            )

        # =================================================================
        # Tab 3: 結果・レポート
        # =================================================================
        with gr.Tab("3. 結果・レポート"):
            gr.Markdown("### 審査結果")

            result_summary = gr.Dataframe(
                label="審査結果サマリー",
                headers=["カテゴリ", "観点名", "重要度", "判定", "理由"],
                interactive=False,
            )

            with gr.Accordion("Markdownレポート全文", open=False):
                report_markdown = gr.Markdown()

            with gr.Row():
                download_md = gr.File(label="Markdownレポート", interactive=False)
                download_html = gr.File(label="HTMLレポート", interactive=False)

    # 審査実行ボタンの接続
    run_btn.click(
        run_governance_review,
        inputs=[review_pdf, review_model],
        outputs=[
            report_markdown,
            result_summary,
            review_status,
            download_md,
            download_html,
        ],
    )


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
