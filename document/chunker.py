"""LLM のコンテキスト制限に対応するチャンク分割モジュール。

セクションを LLM のトークン上限に収まるようにグルーピングする。
セクション単位を極力壊さず、やむを得ない場合のみ段落単位で分割する。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from document.extractor import Section
from config import MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """LLM に一度に渡すテキストチャンク。"""

    sections: list[Section] = field(default_factory=list)
    text: str = ""  # セクション結合後のテキスト


# ---------------------------------------------------------------------------
# トークン数の簡易推定
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """テキストのトークン数を簡易推定する。

    日本語テキストの場合、1 文字あたり約 0.5〜1.0 トークンとなるため、
    安全側に倒して 0.5 係数を使用する。ASCII のみの場合は 0.25 程度だが、
    ガバナンス文書は日本語主体のため 0.5 を採用。
    """
    if not text:
        return 0
    return int(len(text) * 0.5)


# ---------------------------------------------------------------------------
# セクションの段落分割（大きすぎるセクション用）
# ---------------------------------------------------------------------------

def _split_section_by_paragraphs(
    section: Section,
    max_tokens: int,
) -> list[Section]:
    """1 セクションがトークン上限を超える場合、段落単位で分割する。

    段落は空行（2 つ以上の連続改行）で区切る。
    それでも 1 段落が上限を超える場合は、行単位で強制分割する。
    """
    paragraphs = section.content.split("\n\n")

    sub_sections: list[Section] = []
    current_lines: list[str] = []
    current_tokens = 0
    part_num = 1

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)

        # 1 段落自体が max_tokens を超える場合は行単位で分割
        if para_tokens > max_tokens:
            # まず蓄積中のものを吐き出す
            if current_lines:
                sub_sections.append(Section(
                    title=f"{section.title}（{part_num}）" if section.title else f"（{part_num}）",
                    content="\n\n".join(current_lines),
                    page_numbers=list(section.page_numbers),
                ))
                part_num += 1
                current_lines = []
                current_tokens = 0

            # 行単位で分割
            lines = para.split("\n")
            line_buffer: list[str] = []
            line_tokens = 0
            for line in lines:
                lt = _estimate_tokens(line)
                if line_tokens + lt > max_tokens and line_buffer:
                    sub_sections.append(Section(
                        title=f"{section.title}（{part_num}）" if section.title else f"（{part_num}）",
                        content="\n".join(line_buffer),
                        page_numbers=list(section.page_numbers),
                    ))
                    part_num += 1
                    line_buffer = []
                    line_tokens = 0
                line_buffer.append(line)
                line_tokens += lt

            if line_buffer:
                current_lines.append("\n".join(line_buffer))
                current_tokens += line_tokens
            continue

        # 蓄積して上限チェック
        if current_tokens + para_tokens > max_tokens and current_lines:
            sub_sections.append(Section(
                title=f"{section.title}（{part_num}）" if section.title else f"（{part_num}）",
                content="\n\n".join(current_lines),
                page_numbers=list(section.page_numbers),
            ))
            part_num += 1
            current_lines = []
            current_tokens = 0

        current_lines.append(para)
        current_tokens += para_tokens

    # 残りを吐き出す
    if current_lines:
        title = section.title
        if part_num > 1:
            title = f"{section.title}（{part_num}）" if section.title else f"（{part_num}）"
        sub_sections.append(Section(
            title=title,
            content="\n\n".join(current_lines),
            page_numbers=list(section.page_numbers),
        ))

    return sub_sections


# ---------------------------------------------------------------------------
# チャンク構築
# ---------------------------------------------------------------------------

def _build_chunk_text(sections: list[Section]) -> str:
    """セクションリストを結合して 1 つのチャンクテキストにする。"""
    parts: list[str] = []
    for sec in sections:
        if sec.title:
            parts.append(f"## {sec.title}\n\n{sec.content}")
        else:
            parts.append(sec.content)
    return "\n\n".join(parts)


def chunk_sections(
    sections: list[Section],
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[Chunk]:
    """セクションを LLM のコンテキストに収まるようチャンクに分割する。

    - 1 セクションが max_tokens 以内ならそのまま
    - 複数セクションを結合して max_tokens に収まるまで詰める
    - セクション単位を壊さない（セクション途中での分割は避ける）
    - ただし 1 セクションが max_tokens を超える場合は段落単位で分割
    - overlap_tokens 分のテキストを次チャンクの先頭に重複させて文脈を維持

    Parameters
    ----------
    sections : list[Section]
        ``split_into_sections`` で分割されたセクションリスト。
    max_tokens : int, optional
        チャンクの最大トークン数。デフォルトは config.MAX_CHUNK_TOKENS。
    overlap_tokens : int, optional
        チャンク間のオーバーラップトークン数。デフォルトは config.CHUNK_OVERLAP_TOKENS。

    Returns
    -------
    list[Chunk]
        チャンクのリスト。
    """
    if max_tokens is None:
        max_tokens = MAX_CHUNK_TOKENS
    if overlap_tokens is None:
        overlap_tokens = CHUNK_OVERLAP_TOKENS

    if not sections:
        return []

    # まず、大きすぎるセクションを段落単位で事前分割
    prepared: list[Section] = []
    for sec in sections:
        if _estimate_tokens(sec.content) > max_tokens:
            prepared.extend(_split_section_by_paragraphs(sec, max_tokens))
        else:
            prepared.append(sec)

    # セクションをグリーディにチャンクへ詰める
    chunks: list[Chunk] = []
    current_sections: list[Section] = []
    current_tokens = 0

    for sec in prepared:
        sec_tokens = _estimate_tokens(sec.content)

        if current_sections and current_tokens + sec_tokens > max_tokens:
            # 現在のチャンクを確定
            text = _build_chunk_text(current_sections)
            chunks.append(Chunk(sections=list(current_sections), text=text))

            # オーバーラップ: 直前チャンクの末尾セクションを次に持ち越す
            overlap_sections: list[Section] = []
            overlap_total = 0
            for prev_sec in reversed(current_sections):
                prev_tokens = _estimate_tokens(prev_sec.content)
                if overlap_total + prev_tokens <= overlap_tokens:
                    overlap_sections.insert(0, prev_sec)
                    overlap_total += prev_tokens
                else:
                    break

            current_sections = overlap_sections
            current_tokens = overlap_total

        current_sections.append(sec)
        current_tokens += sec_tokens

    # 最後のチャンクを確定
    if current_sections:
        text = _build_chunk_text(current_sections)
        chunks.append(Chunk(sections=list(current_sections), text=text))

    return chunks
