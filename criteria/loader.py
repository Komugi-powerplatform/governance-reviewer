"""審査観点を統一形式にロードするモジュール。

YAML / JSON / CSV / Excel ファイルから審査観点（Criterion）を読み込み、
統一的な dataclass リストとして返す。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

from criteria.parser_structured import parse_yaml_json, parse_csv_excel


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class Criterion:
    """ガバナンス審査の 1 観点を表す。"""

    id: str
    category: str
    name: str
    description: str
    severity: str  # "high" / "medium" / "low"


# ---------------------------------------------------------------------------
# デフォルト YAML のパス
# ---------------------------------------------------------------------------

_DEFAULTS_DIR = Path(__file__).resolve().parent / "defaults"
_DEFAULT_YAML = _DEFAULTS_DIR / "corporate_governance.yaml"


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------

def load_from_yaml(file_path: str) -> list[Criterion]:
    """YAML または JSON ファイルから審査観点を読み込む。

    Parameters
    ----------
    file_path : str
        YAML (.yaml, .yml) または JSON (.json) ファイルのパス。

    Returns
    -------
    list[Criterion]
        パースされた審査観点のリスト。
    """
    return parse_yaml_json(file_path)


def load_from_csv(file_path: str) -> list[Criterion]:
    """CSV または Excel ファイルから審査観点を読み込む。

    カラム名は英語・日本語いずれにも柔軟にマッピングされる。
    詳細は :func:`criteria.parser_structured.parse_csv_excel` を参照。

    Parameters
    ----------
    file_path : str
        CSV (.csv) または Excel (.xlsx, .xls) ファイルのパス。

    Returns
    -------
    list[Criterion]
        パースされた審査観点のリスト。
    """
    return parse_csv_excel(file_path)


def load_defaults() -> list[Criterion]:
    """デフォルト審査観点（corporate_governance.yaml）を読み込む。

    Returns
    -------
    list[Criterion]
        デフォルト YAML に定義された審査観点のリスト。

    Raises
    ------
    FileNotFoundError
        デフォルト YAML が見つからない場合。
    """
    if not _DEFAULT_YAML.exists():
        raise FileNotFoundError(
            f"デフォルト審査観点ファイルが見つかりません: {_DEFAULT_YAML}"
        )
    return parse_yaml_json(str(_DEFAULT_YAML))


def criteria_to_dataframe(criteria: list[Criterion]) -> pd.DataFrame:
    """審査観点を pandas DataFrame に変換する（UI プレビュー用）。

    Parameters
    ----------
    criteria : list[Criterion]
        変換対象の審査観点リスト。

    Returns
    -------
    pd.DataFrame
        カラム: id, category, name, description, severity
    """
    if not criteria:
        return pd.DataFrame(columns=["id", "category", "name", "description", "severity"])

    return pd.DataFrame([asdict(c) for c in criteria])
