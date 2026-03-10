"""PDF から審査観点を抽出するモジュール（LLM 使用）。

PyMuPDF でテキストを抽出し、LLM に審査観点の構造化を依頼して
Criterion リストを返す。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# LLM クライアントのインターフェース定義
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMClient(Protocol):
    """LLM クライアントの最小インターフェース。"""

    async def complete(self, prompt: str) -> str:
        """プロンプトを送信し、テキスト応答を返す。"""
        ...


# ---------------------------------------------------------------------------
# プロンプトテンプレート
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """\
あなたはガバナンス審査の専門家です。
以下の文書テキストから、審査観点（チェック項目）を抽出してください。

## 出力形式

JSON 配列で出力してください。各要素は以下のキーを持つオブジェクトです:

```json
[
  {{
    "id": "C001",
    "category": "カテゴリ名",
    "name": "観点名（簡潔に）",
    "description": "具体的に何を確認するかの説明",
    "severity": "high"
  }}
]
```

## ルール

- severity は "high" / "medium" / "low" のいずれかを選択してください。
- id は C001 から連番で付与してください。
- category は内容に応じて適切に分類してください（例: 情報セキュリティ、個人情報保護、コンプライアンス等）。
- 文書に明示されていない項目は推測せず、文書の記載内容のみを抽出してください。
- JSON 配列のみを出力し、他の説明文は含めないでください。

## 文書テキスト

{document_text}
"""


# ---------------------------------------------------------------------------
# テキスト抽出
# ---------------------------------------------------------------------------

def _extract_text_from_pdf(file_path: str) -> str:
    """PyMuPDF (fitz) を使って PDF からテキストを抽出する。

    Parameters
    ----------
    file_path : str
        PDF ファイルのパス。

    Returns
    -------
    str
        抽出されたテキスト。ページ区切りは改行 2 つで連結。

    Raises
    ------
    ImportError
        PyMuPDF がインストールされていない場合。
    FileNotFoundError
        ファイルが見つからない場合。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError(
            "PDF の読み込みには PyMuPDF が必要です。"
            " `pip install pymupdf` でインストールしてください。"
        ) from e

    doc = fitz.open(file_path)
    pages: list[str] = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages.append(text.strip())
    doc.close()

    if not pages:
        raise ValueError(f"PDF からテキストを抽出できませんでした: {file_path}")

    return "\n\n".join(pages)


# ---------------------------------------------------------------------------
# LLM 応答のパース
# ---------------------------------------------------------------------------

def _parse_llm_response(response: str) -> list[dict[str, Any]]:
    """LLM の応答テキストから JSON 配列を抽出しパースする。

    LLM が JSON 以外のテキスト（説明文やマークダウンコードブロック）を
    含めて返す場合にも対応する。

    Parameters
    ----------
    response : str
        LLM の応答テキスト。

    Returns
    -------
    list[dict[str, Any]]
        パースされた審査観点の辞書リスト。
    """
    # マークダウンコードブロックの中身を抽出
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)```", response, re.DOTALL)
    if code_block_match:
        json_text = code_block_match.group(1).strip()
    else:
        # コードブロックがない場合、最初の [ から最後の ] までを抽出
        bracket_match = re.search(r"\[.*\]", response, re.DOTALL)
        if bracket_match:
            json_text = bracket_match.group(0)
        else:
            json_text = response.strip()

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM の応答を JSON としてパースできませんでした: {e}\n"
            f"応答テキスト (先頭500文字): {response[:500]}"
        ) from e

    if not isinstance(data, list):
        raise ValueError(
            f"LLM の応答がリスト形式ではありません: {type(data)}"
        )

    return data


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------

async def extract_criteria_from_pdf(file_path: str, llm_client: LLMClient) -> list:
    """PDF から審査観点を抽出する（LLM を使用）。

    処理フロー:
    1. PyMuPDF で PDF テキストを抽出
    2. LLM に「この文書から審査観点を抽出してください」とプロンプト送信
    3. LLM 応答をパースして Criterion リストに変換

    Parameters
    ----------
    file_path : str
        PDF ファイルのパス。
    llm_client : LLMClient
        ``async def complete(prompt: str) -> str`` を持つ LLM クライアント。

    Returns
    -------
    list[Criterion]
        抽出された審査観点のリスト。
    """
    from criteria.loader import Criterion

    # 1. PDF からテキスト抽出
    document_text = _extract_text_from_pdf(file_path)

    # テキストが非常に長い場合は切り詰める（LLM のコンテキスト長制限を考慮）
    max_chars = 50_000
    if len(document_text) > max_chars:
        document_text = document_text[:max_chars] + "\n\n[... 以降省略 ...]"

    # 2. LLM にプロンプト送信
    prompt = _EXTRACTION_PROMPT.format(document_text=document_text)
    response = await llm_client.complete(prompt)

    # 3. 応答をパースして Criterion リストに変換
    items = _parse_llm_response(response)

    results: list[Criterion] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        severity_raw = str(item.get("severity", "medium")).lower()
        if severity_raw not in ("high", "medium", "low"):
            severity_raw = "medium"

        results.append(
            Criterion(
                id=str(item.get("id", f"C{i + 1:03d}")).strip(),
                category=str(item.get("category", "未分類")).strip(),
                name=str(item.get("name", "")).strip(),
                description=str(item.get("description", "")).strip(),
                severity=severity_raw,
            )
        )

    return results
