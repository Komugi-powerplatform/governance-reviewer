"""litellm 経由の LLM クライアントモジュール。

litellm を使用して複数の LLM プロバイダ（Anthropic, OpenAI 等）に
統一インターフェースでアクセスする。
"""

from __future__ import annotations

import json
import logging

import litellm

from config import DEFAULT_MODEL

logger = logging.getLogger(__name__)


class LLMClient:
    """litellm 経由の LLM クライアント。

    Parameters
    ----------
    model : str, optional
        litellm のモデル名（例: "claude-sonnet-4-20250514", "gpt-4o"）。
        省略時は config.DEFAULT_MODEL を使用。
    """

    def __init__(self, model: str | None = None):
        self.model = model or DEFAULT_MODEL

    async def complete(self, prompt: str) -> str:
        """プロンプトを送信してテキスト応答を取得する。

        Parameters
        ----------
        prompt : str
            LLM に送信するプロンプト。

        Returns
        -------
        str
            LLM のテキスト応答。

        Raises
        ------
        RuntimeError
            LLM 呼び出しが失敗した場合。
        """
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("LLM 呼び出しに失敗しました (model=%s): %s", self.model, e)
            raise RuntimeError(
                f"LLM 呼び出しに失敗しました (model={self.model}): {e}"
            ) from e

    async def complete_json(self, prompt: str) -> dict:
        """JSON 応答を期待するプロンプトを送信し、辞書で返す。

        LLM の応答テキストから JSON をパースする。応答にマークダウンの
        コードブロックが含まれている場合も適切に処理する。

        Parameters
        ----------
        prompt : str
            JSON 形式での応答を期待するプロンプト。

        Returns
        -------
        dict
            パースされた JSON オブジェクト。

        Raises
        ------
        RuntimeError
            LLM 呼び出しまたは JSON パースに失敗した場合。
        """
        raw = await self.complete(prompt)
        return _parse_json_response(raw)


def _parse_json_response(text: str) -> dict:
    """LLM のテキスト応答から JSON オブジェクトを抽出・パースする。

    マークダウンコードブロック（```json ... ```）や余分なテキストが
    含まれている場合にも対応する。

    Parameters
    ----------
    text : str
        LLM の応答テキスト。

    Returns
    -------
    dict
        パースされた JSON オブジェクト（dict or list）。
    """
    import re

    # マークダウンコードブロックの中身を抽出
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if code_block_match:
        json_text = code_block_match.group(1).strip()
    else:
        # コードブロックがない場合、最初の { or [ から対応する閉じ括弧まで抽出
        brace_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if brace_match:
            json_text = brace_match.group(1)
        else:
            json_text = text.strip()

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM の応答を JSON としてパースできませんでした: {e}\n"
            f"応答テキスト (先頭500文字): {text[:500]}"
        ) from e
