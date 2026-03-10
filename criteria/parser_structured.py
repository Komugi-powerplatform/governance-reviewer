"""構造化ファイル（YAML / JSON / CSV / Excel）から審査観点をパースするモジュール。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml
import pandas as pd


# ---------------------------------------------------------------------------
# Criterion は loader.py で定義されているが、循環 import を避けるため
# ここでは軽量に再構築して返す。loader.py 側で同じ dataclass を使う。
# ---------------------------------------------------------------------------

def _make_criterion(
    id: str,
    category: str,
    name: str,
    description: str,
    severity: str,
):
    """Criterion dataclass のインスタンスを生成する（遅延 import で循環回避）。"""
    from criteria.loader import Criterion

    return Criterion(
        id=str(id).strip(),
        category=str(category).strip(),
        name=str(name).strip(),
        description=str(description).strip(),
        severity=_normalize_severity(str(severity).strip()),
    )


# ---------------------------------------------------------------------------
# 内部ユーティリティ
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = {"high", "medium", "low"}


def _normalize_severity(value: str) -> str:
    """severity 値を正規化する。日本語表記にも対応。"""
    lower = value.lower()
    if lower in _VALID_SEVERITIES:
        return lower

    # 日本語マッピング
    ja_map = {
        "高": "high",
        "中": "medium",
        "低": "low",
    }
    if lower in ja_map:
        return ja_map[lower]

    # フォールバック: 不明な場合は medium
    return "medium"


# カラム名のマッピング定義（日本語 → 英語正規名）
_COLUMN_ALIASES: dict[str, list[str]] = {
    "id": ["id", "ID", "番号", "No", "no", "No."],
    "category": ["category", "カテゴリ", "分類", "Category"],
    "name": ["name", "観点名", "項目名", "チェック項目", "Name", "項目"],
    "description": ["description", "説明", "詳細", "確認内容", "Description", "内容"],
    "severity": ["severity", "重要度", "優先度", "Severity", "レベル"],
}


def _resolve_column_name(columns: list[str], target: str) -> str | None:
    """実際のカラム名一覧から、target に対応するカラム名を見つける。"""
    aliases = _COLUMN_ALIASES.get(target, [])
    for alias in aliases:
        if alias in columns:
            return alias
    return None


def _build_column_map(columns: list[str]) -> dict[str, str]:
    """DataFrame のカラム名から正規カラム名へのマッピングを構築する。

    Returns
    -------
    dict[str, str]
        {実際のカラム名: 正規カラム名} のマッピング。

    Raises
    ------
    ValueError
        必須カラム（name）が見つからない場合。
    """
    mapping: dict[str, str] = {}
    for canonical in ["id", "category", "name", "description", "severity"]:
        actual = _resolve_column_name(columns, canonical)
        if actual is not None:
            mapping[actual] = canonical

    # name は必須
    if "name" not in mapping.values():
        raise ValueError(
            f"必須カラム 'name' に対応するカラムが見つかりません。"
            f" 検出されたカラム: {columns}"
        )

    return mapping


# ---------------------------------------------------------------------------
# YAML / JSON パーサー
# ---------------------------------------------------------------------------

def parse_yaml_json(file_path: str) -> list:
    """YAML または JSON ファイルから Criterion リストを生成する。

    ファイル形式は拡張子で判定する。
    YAML/JSON のトップレベルに ``criteria`` キーがある場合はその配列を使用し、
    トップレベルがリストの場合はそのまま使用する。

    Parameters
    ----------
    file_path : str
        読み込むファイルのパス。

    Returns
    -------
    list[Criterion]
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        # 拡張子不明の場合は YAML として試みる
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            data = json.loads(text)

    return _parse_criteria_data(data)


def _parse_criteria_data(data: Any) -> list:
    """パース済みデータ（dict or list）から Criterion リストを生成する。"""
    if isinstance(data, dict):
        # "criteria" キーがあればその中身を使う
        if "criteria" in data:
            items = data["criteria"]
        else:
            # dict のトップレベルに criteria が無い場合、値を探索
            raise ValueError(
                "YAML/JSON のトップレベルに 'criteria' キーが見つかりません。"
            )
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError(f"予期しないデータ形式です: {type(data)}")

    results = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"criteria[{i}] が dict ではありません: {type(item)}")

        results.append(
            _make_criterion(
                id=item.get("id", f"C{i + 1:03d}"),
                category=item.get("category", "未分類"),
                name=item.get("name", ""),
                description=item.get("description", ""),
                severity=item.get("severity", "medium"),
            )
        )

    return results


# ---------------------------------------------------------------------------
# CSV / Excel パーサー
# ---------------------------------------------------------------------------

def parse_csv_excel(file_path: str) -> list:
    """CSV または Excel ファイルから Criterion リストを生成する。

    カラム名の日本語マッピング:
    - "ID" / "id" / "番号" -> id
    - "カテゴリ" / "category" / "分類" -> category
    - "観点名" / "name" / "項目名" / "チェック項目" -> name
    - "説明" / "description" / "詳細" / "確認内容" -> description
    - "重要度" / "severity" / "優先度" -> severity

    Parameters
    ----------
    file_path : str
        読み込むファイルのパス。

    Returns
    -------
    list[Criterion]
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(file_path, encoding="utf-8-sig", dtype=str)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, dtype=str)
    else:
        raise ValueError(
            f"サポートされていないファイル形式です: {suffix}"
            " (.csv, .xlsx, .xls のいずれかを指定してください)"
        )

    # 空行を除去
    df = df.dropna(how="all").reset_index(drop=True)

    # カラム名マッピング
    column_map = _build_column_map(list(df.columns))
    df = df.rename(columns=column_map)

    results = []
    for i, row in df.iterrows():
        results.append(
            _make_criterion(
                id=row.get("id", f"C{i + 1:03d}") or f"C{i + 1:03d}",
                category=row.get("category", "未分類") or "未分類",
                name=row.get("name", "") or "",
                description=row.get("description", "") or "",
                severity=row.get("severity", "medium") or "medium",
            )
        )

    return results
