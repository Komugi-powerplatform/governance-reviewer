"""審査実行エンジンモジュール。

全審査観点 x 全チャンクで LLM 判定を実行し、結果を集約する。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

from criteria.loader import Criterion
from document.chunker import Chunk
from analysis.llm_client import LLMClient
from analysis.prompts import build_review_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 判定の優先度（厳しい順）
# ---------------------------------------------------------------------------

_JUDGMENT_SEVERITY_ORDER = {
    "fail": 0,
    "warning": 1,
    "pass": 2,
    "na": 3,
}


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class ReviewResult:
    """1 つの審査観点に対する判定結果。"""

    criterion_id: str
    criterion_name: str
    criterion_category: str
    criterion_severity: str
    judgment: str       # "pass" / "warning" / "fail" / "na"
    evidence: str       # 文書からの引用
    reason: str         # 判定理由
    recommendation: str  # 改善提案


# ---------------------------------------------------------------------------
# 単一チャンクの審査
# ---------------------------------------------------------------------------

async def _review_single(
    criterion: Criterion,
    chunk: Chunk,
    llm_client: LLMClient,
) -> ReviewResult:
    """1 つの観点 x 1 つのチャンクで LLM 判定を実行する。

    LLM 応答が JSON としてパースできない場合は warning 判定とし、
    応答テキストを reason に含めて返す。
    """
    prompt = build_review_prompt(
        criterion_name=criterion.name,
        criterion_description=criterion.description,
        document_text=chunk.text,
    )

    try:
        result_dict = await llm_client.complete_json(prompt)
    except RuntimeError as e:
        logger.warning(
            "LLM 応答のパースに失敗しました (criterion=%s): %s",
            criterion.id, e,
        )
        return ReviewResult(
            criterion_id=criterion.id,
            criterion_name=criterion.name,
            criterion_category=criterion.category,
            criterion_severity=criterion.severity,
            judgment="warning",
            evidence="",
            reason=f"LLM 応答のパースに失敗: {e}",
            recommendation="手動で確認してください。",
        )

    # 判定値の正規化
    judgment_raw = str(result_dict.get("judgment", "na")).lower().strip()
    if judgment_raw not in _JUDGMENT_SEVERITY_ORDER:
        judgment_raw = "warning"

    return ReviewResult(
        criterion_id=criterion.id,
        criterion_name=criterion.name,
        criterion_category=criterion.category,
        criterion_severity=criterion.severity,
        judgment=judgment_raw,
        evidence=str(result_dict.get("evidence", "")).strip(),
        reason=str(result_dict.get("reason", "")).strip(),
        recommendation=str(result_dict.get("recommendation", "")).strip(),
    )


# ---------------------------------------------------------------------------
# 複数チャンクの結果集約
# ---------------------------------------------------------------------------

def _merge_results(results: list[ReviewResult]) -> ReviewResult:
    """同一観点の複数チャンク結果を集約する。

    最も厳しい判定を採用し、evidence と reason は結合する。
    """
    if len(results) == 1:
        return results[0]

    # 最も厳しい判定を選択
    sorted_results = sorted(
        results,
        key=lambda r: _JUDGMENT_SEVERITY_ORDER.get(r.judgment, 3),
    )
    worst = sorted_results[0]

    # 有意義な evidence と reason を集める
    evidences = [r.evidence for r in results if r.evidence]
    reasons = [r.reason for r in results if r.reason]
    recommendations = [r.recommendation for r in results if r.recommendation]

    return ReviewResult(
        criterion_id=worst.criterion_id,
        criterion_name=worst.criterion_name,
        criterion_category=worst.criterion_category,
        criterion_severity=worst.criterion_severity,
        judgment=worst.judgment,
        evidence="\n---\n".join(evidences) if evidences else "",
        reason="\n".join(reasons) if reasons else "",
        recommendation="\n".join(dict.fromkeys(recommendations)) if recommendations else "",
    )


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------

async def run_review(
    criteria: list[Criterion],
    chunks: list[Chunk],
    llm_client: LLMClient,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[ReviewResult]:
    """全観点 x 全チャンクで審査を実行する。

    各観点について、全チャンクに対して LLM 判定を実行し、
    複数チャンクにまたがる場合は最も厳しい判定を採用する。

    Parameters
    ----------
    criteria : list[Criterion]
        審査観点のリスト。
    chunks : list[Chunk]
        文書チャンクのリスト。
    llm_client : LLMClient
        LLM クライアント。
    progress_callback : callable, optional
        進捗通知コールバック。``callback(current, total)`` 形式で呼ばれる。

    Returns
    -------
    list[ReviewResult]
        審査結果のリスト（観点ごとに 1 件）。
    """
    total_tasks = len(criteria) * len(chunks)
    current_task = 0
    final_results: list[ReviewResult] = []

    for criterion in criteria:
        chunk_results: list[ReviewResult] = []

        for chunk in chunks:
            result = await _review_single(criterion, chunk, llm_client)
            chunk_results.append(result)

            current_task += 1
            if progress_callback is not None:
                progress_callback(current_task, total_tasks)

        # 複数チャンクの結果を集約
        merged = _merge_results(chunk_results)
        final_results.append(merged)

    return final_results
