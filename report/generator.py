"""審査結果からレポートを生成するモジュール。

Markdown / HTML / DataFrame 形式でレポートを出力する。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from analysis.engine import ReviewResult
from criteria.loader import Criterion
import config

# ---------------------------------------------------------------------------
# テンプレートディレクトリ
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _judgment_icon(judgment: str) -> str:
    """judgment キーに対応するアイコン付きラベルを返す。"""
    return config.JUDGMENTS.get(judgment, judgment)


def _severity_label(severity: str) -> str:
    """severity キーに対応するアイコン付きラベルを返す。"""
    return config.SEVERITY_LABELS.get(severity, severity)


def _group_by_category(
    results: list[ReviewResult],
) -> dict[str, list[ReviewResult]]:
    """結果をカテゴリごとにグループ化する（出現順を保持）。"""
    groups: dict[str, list[ReviewResult]] = {}
    for r in results:
        groups.setdefault(r.criterion_category, []).append(r)
    return groups


def _compute_stats(results: list[ReviewResult]) -> dict:
    """サマリー統計を計算する。"""
    total = len(results)
    counts = defaultdict(int)
    for r in results:
        counts[r.judgment] += 1

    pass_count = counts.get("pass", 0)
    applicable = total - counts.get("na", 0)
    compliance_rate = (pass_count / applicable * 100) if applicable > 0 else 0.0

    return {
        "total": total,
        "pass": pass_count,
        "warning": counts.get("warning", 0),
        "fail": counts.get("fail", 0),
        "na": counts.get("na", 0),
        "applicable": applicable,
        "compliance_rate": compliance_rate,
    }


def _compute_category_stats(
    grouped: dict[str, list[ReviewResult]],
) -> list[dict]:
    """カテゴリ別の統計テーブル用データを生成する。"""
    rows = []
    for category, items in grouped.items():
        stats = _compute_stats(items)
        rows.append({
            "category": category,
            "total": stats["total"],
            "pass": stats["pass"],
            "warning": stats["warning"],
            "fail": stats["fail"],
            "na": stats["na"],
            "compliance_rate": stats["compliance_rate"],
        })
    return rows


# ---------------------------------------------------------------------------
# Markdown レポート
# ---------------------------------------------------------------------------


def generate_markdown_report(
    results: list[ReviewResult],
    document_name: str = "審査対象文書",
) -> str:
    """審査結果を Markdown レポートに変換する。

    レポート構成:
    1. ヘッダー（タイトル、審査日時、対象文書名）
    2. サマリー（合計観点数、適合/要確認/不適合/該当なしの内訳、適合率）
    3. カテゴリ別サマリーテーブル
    4. 詳細結果（カテゴリごとにグループ化）
       - 各観点: 判定アイコン、観点名、重要度、理由、引用、改善提案
    5. 不適合・要確認項目のピックアップ（アクションアイテム）

    Parameters
    ----------
    results : list[ReviewResult]
        審査結果のリスト。
    document_name : str
        対象文書名。

    Returns
    -------
    str
        Markdown 形式のレポート文字列。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    stats = _compute_stats(results)
    grouped = _group_by_category(results)
    category_stats = _compute_category_stats(grouped)

    lines: list[str] = []

    # ── 1. ヘッダー ──
    lines.append("# ガバナンス審査レポート")
    lines.append("")
    lines.append(f"- **審査日時**: {now}")
    lines.append(f"- **対象文書**: {document_name}")
    lines.append("")

    # ── 2. サマリー ──
    lines.append("## サマリー")
    lines.append("")
    lines.append(f"| 項目 | 値 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 審査観点数 | {stats['total']} |")
    lines.append(f"| {_judgment_icon('pass')} | {stats['pass']} |")
    lines.append(f"| {_judgment_icon('warning')} | {stats['warning']} |")
    lines.append(f"| {_judgment_icon('fail')} | {stats['fail']} |")
    lines.append(f"| {_judgment_icon('na')} | {stats['na']} |")
    lines.append(f"| **適合率** | **{stats['compliance_rate']:.1f}%** |")
    lines.append("")

    # ── 3. カテゴリ別サマリー ──
    lines.append("## カテゴリ別サマリー")
    lines.append("")
    lines.append("| カテゴリ | 観点数 | 適合 | 要確認 | 不適合 | 該当なし | 適合率 |")
    lines.append("|----------|--------|------|--------|--------|----------|--------|")
    for cs in category_stats:
        lines.append(
            f"| {cs['category']} "
            f"| {cs['total']} "
            f"| {cs['pass']} "
            f"| {cs['warning']} "
            f"| {cs['fail']} "
            f"| {cs['na']} "
            f"| {cs['compliance_rate']:.1f}% |"
        )
    lines.append("")

    # ── 4. 詳細結果 ──
    lines.append("## 詳細結果")
    lines.append("")

    for category, items in grouped.items():
        lines.append(f"### {category}")
        lines.append("")

        for r in items:
            lines.append(f"#### {_judgment_icon(r.judgment)} {r.criterion_name}")
            lines.append("")
            lines.append(f"- **重要度**: {_severity_label(r.criterion_severity)}")
            lines.append(f"- **判定**: {_judgment_icon(r.judgment)}")
            lines.append("")

            if r.reason:
                lines.append(f"**理由**: {r.reason}")
                lines.append("")

            if r.evidence:
                lines.append("**引用**:")
                lines.append("")
                lines.append(f"> {r.evidence}")
                lines.append("")

            if r.recommendation:
                lines.append(f"**改善提案**: {r.recommendation}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # ── 5. アクションアイテム ──
    action_items = [
        r for r in results if r.judgment in ("fail", "warning")
    ]

    if action_items:
        lines.append("## アクションアイテム")
        lines.append("")
        lines.append("以下の項目は対応が必要です。")
        lines.append("")

        # 不適合を先に表示
        action_items_sorted = sorted(
            action_items,
            key=lambda r: (0 if r.judgment == "fail" else 1, r.criterion_severity != "high"),
        )

        for i, r in enumerate(action_items_sorted, 1):
            lines.append(
                f"{i}. {_judgment_icon(r.judgment)} "
                f"**{r.criterion_name}**（{_severity_label(r.criterion_severity)}）"
            )
            if r.recommendation:
                lines.append(f"   - {r.recommendation}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# サマリー DataFrame（Gradio UI 用）
# ---------------------------------------------------------------------------


def generate_summary_dataframe(results: list[ReviewResult]) -> pd.DataFrame:
    """Gradio UI 表示用のサマリー DataFrame を生成する。

    Parameters
    ----------
    results : list[ReviewResult]
        審査結果のリスト。

    Returns
    -------
    pd.DataFrame
        カラム: カテゴリ, 観点名, 重要度, 判定, 理由
        判定はアイコン付き文字列。
    """
    if not results:
        return pd.DataFrame(
            columns=["カテゴリ", "観点名", "重要度", "判定", "理由"]
        )

    rows = []
    for r in results:
        rows.append({
            "カテゴリ": r.criterion_category,
            "観点名": r.criterion_name,
            "重要度": _severity_label(r.criterion_severity),
            "判定": _judgment_icon(r.judgment),
            "理由": r.reason,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 個別詳細 HTML（Gradio UI 用）
# ---------------------------------------------------------------------------


def generate_detail_html(result: ReviewResult) -> str:
    """個別の審査結果を詳細 HTML として出力する（Gradio 表示用）。

    引用・理由・改善提案を含む。

    Parameters
    ----------
    result : ReviewResult
        個別の審査結果。

    Returns
    -------
    str
        HTML 文字列。
    """
    judgment_colors = {
        "pass": "#16a34a",
        "warning": "#ca8a04",
        "fail": "#dc2626",
        "na": "#6b7280",
    }
    color = judgment_colors.get(result.judgment, "#6b7280")

    parts: list[str] = []
    parts.append(
        f'<div style="border-left: 4px solid {color}; padding: 12px 16px; '
        f'margin: 8px 0; background: #fafafa; border-radius: 4px;">'
    )
    parts.append(
        f'<h3 style="margin: 0 0 8px 0; color: {color};">'
        f'{_judgment_icon(result.judgment)} {result.criterion_name}</h3>'
    )
    parts.append(
        f'<p style="margin: 4px 0; font-size: 0.9em; color: #555;">'
        f'<strong>重要度:</strong> {_severity_label(result.criterion_severity)} '
        f'&nbsp;|&nbsp; '
        f'<strong>カテゴリ:</strong> {result.criterion_category}</p>'
    )

    if result.reason:
        parts.append(
            f'<p style="margin: 8px 0;"><strong>理由:</strong> {result.reason}</p>'
        )

    if result.evidence:
        parts.append(
            f'<blockquote style="margin: 8px 0; padding: 8px 12px; '
            f'background: #f0f0f0; border-left: 3px solid #ccc; '
            f'font-size: 0.9em; color: #444;">'
            f'{result.evidence}</blockquote>'
        )

    if result.recommendation:
        parts.append(
            f'<p style="margin: 8px 0; padding: 8px 12px; '
            f'background: #eff6ff; border-radius: 4px;">'
            f'<strong>改善提案:</strong> {result.recommendation}</p>'
        )

    parts.append("</div>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML レポート（Jinja2 テンプレート）
# ---------------------------------------------------------------------------


def generate_html_report(
    results: list[ReviewResult],
    document_name: str = "審査対象文書",
) -> str:
    """Jinja2 テンプレートを使った HTML レポートを生成する。

    Parameters
    ----------
    results : list[ReviewResult]
        審査結果のリスト。
    document_name : str
        対象文書名。

    Returns
    -------
    str
        HTML 文字列。
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template("review_report.html")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    stats = _compute_stats(results)
    grouped = _group_by_category(results)
    category_stats = _compute_category_stats(grouped)

    # 不適合・要確認のアクションアイテム
    action_items = sorted(
        [r for r in results if r.judgment in ("fail", "warning")],
        key=lambda r: (0 if r.judgment == "fail" else 1, r.criterion_severity != "high"),
    )

    return template.render(
        document_name=document_name,
        review_datetime=now,
        stats=stats,
        category_stats=category_stats,
        grouped=grouped,
        action_items=action_items,
        judgment_icon=_judgment_icon,
        severity_label=_severity_label,
        judgments=config.JUDGMENTS,
        severity_labels=config.SEVERITY_LABELS,
    )
