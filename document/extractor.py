"""審査対象 PDF からテキストを抽出し、セクション分割するモジュール。

PyMuPDF でテキストを抽出した後、日本語の規程文書に多い見出しパターンを
検出してセクションに分割する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """文書の 1 セクションを表す。"""

    title: str              # セクション見出し（「第1章 総則」等）
    content: str            # セクション本文
    page_numbers: list[int] = field(default_factory=list)  # 含まれるページ番号


# ---------------------------------------------------------------------------
# 見出しパターン定義
# ---------------------------------------------------------------------------

# 日本語の規程文書に多い見出しパターン（優先度順）
_HEADING_PATTERNS: list[re.Pattern] = [
    # 「第X章」「第X条」「第X項」「第X節」（半角・全角数字）
    re.compile(r"^第[0-9０-９一二三四五六七八九十百]+[章条項節編]"),
    # 「1.」「1.1」「1.1.1」等の番号付き見出し
    re.compile(r"^[0-9０-９]+(?:\.[0-9０-９]+)*[\.\s　]"),
    # 「(1)」「（1）」等の括弧番号
    re.compile(r"^[\(（][0-9０-９]+[\)）]"),
    # 「附則」「別表」等の特殊セクション
    re.compile(r"^(?:附則|別表|付則|別紙|前文)"),
]


def _is_heading(line: str) -> bool:
    """行が見出しパターンに一致するか判定する。"""
    stripped = line.strip()
    if not stripped:
        return False
    for pattern in _HEADING_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


# ---------------------------------------------------------------------------
# テキスト抽出
# ---------------------------------------------------------------------------

def extract_text(file_path: str) -> str:
    """PyMuPDF で PDF からテキスト全文を抽出する。

    Parameters
    ----------
    file_path : str
        PDF ファイルのパス。

    Returns
    -------
    str
        抽出されたテキスト。各ページは ``\\n--- PAGE {n} ---\\n`` で区切られる。

    Raises
    ------
    ImportError
        PyMuPDF がインストールされていない場合。
    FileNotFoundError
        ファイルが見つからない場合。
    ValueError
        PDF からテキストを抽出できなかった場合。
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
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages.append(f"--- PAGE {i + 1} ---\n{text.strip()}")
    doc.close()

    if not pages:
        raise ValueError(f"PDF からテキストを抽出できませんでした: {file_path}")

    return "\n\n".join(pages)


# ---------------------------------------------------------------------------
# セクション分割
# ---------------------------------------------------------------------------

def _extract_page_number(text: str) -> int | None:
    """テキスト中の PAGE マーカーからページ番号を抽出する。"""
    match = re.search(r"--- PAGE (\d+) ---", text)
    if match:
        return int(match.group(1))
    return None


def _build_page_map(full_text: str) -> list[tuple[int, int, int]]:
    """テキスト全体から (start_pos, end_pos, page_number) のリストを構築する。"""
    page_map: list[tuple[int, int, int]] = []
    for match in re.finditer(r"--- PAGE (\d+) ---", full_text):
        page_num = int(match.group(1))
        start = match.start()
        page_map.append((start, 0, page_num))  # end は後で埋める

    # end を設定
    result: list[tuple[int, int, int]] = []
    for i, (start, _, page_num) in enumerate(page_map):
        if i + 1 < len(page_map):
            end = page_map[i + 1][0]
        else:
            end = len(full_text)
        result.append((start, end, page_num))

    return result


def _get_page_numbers_for_range(
    page_map: list[tuple[int, int, int]],
    start_pos: int,
    end_pos: int,
) -> list[int]:
    """テキスト中の位置範囲に対応するページ番号のリストを返す。"""
    pages: list[int] = []
    for seg_start, seg_end, page_num in page_map:
        # 範囲が重なるページを収集
        if seg_start < end_pos and seg_end > start_pos:
            if page_num not in pages:
                pages.append(page_num)
    return pages


def split_into_sections(text: str) -> list[Section]:
    """テキストをセクションに分割する。

    日本語の規程文書に多い見出しパターンを検出:
    - 「第X章」「第X条」「第X項」
    - 「1.」「1.1」「(1)」等の番号付き見出し
    - 全角数字のパターンも対応

    見出しが検出できない場合はページ単位でフォールバックする。

    Parameters
    ----------
    text : str
        ``extract_text`` で抽出されたテキスト（PAGE マーカー付き）。

    Returns
    -------
    list[Section]
        分割されたセクションのリスト。
    """
    page_map = _build_page_map(text)

    # PAGE マーカーを除去した行ごとに見出し検出
    # ただし位置情報は元テキスト基準で保持
    lines = text.split("\n")
    sections: list[Section] = []
    current_title = ""
    current_lines: list[str] = []
    current_start_pos = 0

    pos = 0  # 元テキスト中の現在位置
    for line in lines:
        line_start = pos
        pos += len(line) + 1  # +1 for newline

        # PAGE マーカー行はスキップ（セクション内容には含めない）
        if re.match(r"^--- PAGE \d+ ---$", line.strip()):
            continue

        if _is_heading(line):
            # 現在蓄積中のセクションを保存
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    page_nums = _get_page_numbers_for_range(
                        page_map, current_start_pos, line_start,
                    )
                    sections.append(Section(
                        title=current_title,
                        content=content,
                        page_numbers=page_nums,
                    ))

            # 新セクション開始
            current_title = line.strip()
            current_lines = []
            current_start_pos = line_start
        else:
            current_lines.append(line)

    # 最後のセクションを保存
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            page_nums = _get_page_numbers_for_range(
                page_map, current_start_pos, len(text),
            )
            sections.append(Section(
                title=current_title,
                content=content,
                page_numbers=page_nums,
            ))

    # 見出しが 1 つも検出できなかった場合はページ単位でフォールバック
    if not sections or (len(sections) == 1 and not sections[0].title):
        return _fallback_split_by_page(text, page_map)

    return sections


def _fallback_split_by_page(
    text: str,
    page_map: list[tuple[int, int, int]],
) -> list[Section]:
    """見出し検出に失敗した場合、ページ単位でセクションを生成する。"""
    sections: list[Section] = []
    for start, end, page_num in page_map:
        raw = text[start:end]
        # PAGE マーカーを除去
        content = re.sub(r"--- PAGE \d+ ---\n?", "", raw).strip()
        if content:
            sections.append(Section(
                title=f"ページ {page_num}",
                content=content,
                page_numbers=[page_num],
            ))
    return sections


# ---------------------------------------------------------------------------
# 一括処理
# ---------------------------------------------------------------------------

def extract_and_split(file_path: str) -> list[Section]:
    """PDF からテキストを抽出し、セクションに分割する一括処理。

    Parameters
    ----------
    file_path : str
        PDF ファイルのパス。

    Returns
    -------
    list[Section]
        分割されたセクションのリスト。
    """
    text = extract_text(file_path)
    return split_into_sections(text)
