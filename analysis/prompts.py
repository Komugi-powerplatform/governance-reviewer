"""審査用プロンプトテンプレートモジュール。

LLM に送信する各種プロンプトを生成する関数を提供する。
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 審査判定プロンプト
# ---------------------------------------------------------------------------

_REVIEW_PROMPT_TEMPLATE = """\
あなたはガバナンス審査の専門家です。
以下の審査観点に基づいて、提示された文書テキストを審査してください。

## 審査観点

- **観点名**: {criterion_name}
- **確認内容**: {criterion_description}

## 審査対象テキスト

{document_text}

## 出力形式

以下の JSON 形式で結果を出力してください。JSON のみを出力し、他の説明文は含めないでください。

```json
{{
  "judgment": "pass",
  "evidence": "文書内の該当箇所の引用（原文ママ）",
  "reason": "判定理由の説明",
  "recommendation": "改善提案（適合・該当なしの場合は空文字列）"
}}
```

## 判定基準

- **pass**: 文書がこの観点の要件を満たしている
- **warning**: 要件を満たしている可能性はあるが、記載が不十分または曖昧な箇所がある
- **fail**: 文書がこの観点の要件を満たしていない、または重大な不備がある
- **na**: この観点が文書の対象範囲外であり、該当しない

## ルール

- evidence は文書テキストからの直接引用としてください（原文ママ）。該当箇所がない場合は空文字列としてください。
- reason は判定の根拠を具体的に説明してください。
- recommendation は judgment が "warning" または "fail" の場合のみ記載してください。"pass" または "na" の場合は空文字列としてください。
- 文書に記載されていない内容を推測で判定しないでください。
"""


def build_review_prompt(
    criterion_name: str,
    criterion_description: str,
    document_text: str,
) -> str:
    """単一の審査観点に対する判定プロンプトを生成する。

    Parameters
    ----------
    criterion_name : str
        審査観点の名称。
    criterion_description : str
        審査観点の詳細説明（確認内容）。
    document_text : str
        審査対象のテキスト（チャンク）。

    Returns
    -------
    str
        LLM に送信するプロンプト文字列。
    """
    return _REVIEW_PROMPT_TEMPLATE.format(
        criterion_name=criterion_name,
        criterion_description=criterion_description,
        document_text=document_text,
    )


# ---------------------------------------------------------------------------
# 審査基準書からの観点抽出プロンプト
# ---------------------------------------------------------------------------

_CRITERIA_EXTRACTION_PROMPT = """\
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
  - high: 法令違反・重大なリスクに直結する項目
  - medium: 推奨事項・ベストプラクティスに関する項目
  - low: 形式的・軽微な確認事項
- id は C001 から連番で付与してください。
- category は内容に応じて適切に分類してください（例: 情報セキュリティ、個人情報保護、コンプライアンス等）。
- 文書に明示されていない項目は推測せず、文書の記載内容のみを抽出してください。
- JSON 配列のみを出力し、他の説明文は含めないでください。

## 文書テキスト

{document_text}
"""


def build_criteria_extraction_prompt(document_text: str) -> str:
    """PDF 審査基準書から審査観点を抽出するプロンプトを生成する。

    Parameters
    ----------
    document_text : str
        審査基準書のテキスト。

    Returns
    -------
    str
        LLM に送信するプロンプト文字列。
    """
    return _CRITERIA_EXTRACTION_PROMPT.format(document_text=document_text)


# ---------------------------------------------------------------------------
# 自由入力テキストからの観点構造化プロンプト
# ---------------------------------------------------------------------------

_TEXT_TO_CRITERIA_PROMPT = """\
あなたはガバナンス審査の専門家です。
ユーザーが入力した以下のテキストを、構造化された審査観点リストに変換してください。

## ユーザー入力

{user_text}

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

- ユーザーの入力が箇条書き・自由文のいずれであっても、個別の審査観点に分解してください。
- severity は "high" / "medium" / "low" のいずれかを、内容の重要度から判断して選択してください。
- id は C001 から連番で付与してください。
- category は内容に応じて適切に分類してください。
- ユーザーが明示していない内容を追加しないでください。
- JSON 配列のみを出力し、他の説明文は含めないでください。
"""


def build_text_to_criteria_prompt(user_text: str) -> str:
    """自由入力テキストから審査観点を構造化するプロンプトを生成する。

    Parameters
    ----------
    user_text : str
        ユーザーが入力した自由テキスト（箇条書き、文章等）。

    Returns
    -------
    str
        LLM に送信するプロンプト文字列。
    """
    return _TEXT_TO_CRITERIA_PROMPT.format(user_text=user_text)
