"""E2Eテスト: PDF解析 → 審査 → レポート生成（LLMモック使用）"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from criteria.loader import load_defaults, criteria_to_dataframe
from document.extractor import extract_and_split
from document.chunker import chunk_sections
from analysis.engine import run_review, ReviewResult
from report.generator import (
    generate_markdown_report,
    generate_html_report,
    generate_summary_dataframe,
)


# ---------------------------------------------------------------------------
# モックLLMクライアント
# ---------------------------------------------------------------------------
class MockLLMClient:
    """LLM呼び出しをモックし、固定の審査結果を返す"""

    call_count = 0

    async def complete(self, prompt: str) -> str:
        self.call_count += 1
        # プロンプトから観点名を抽出して判定を振り分け
        if "パスワード" in prompt:
            result = {
                "judgment": "warning",
                "evidence": "パスワードは8文字以上、英数字を含む、90日ごとに変更",
                "reason": "パスワード要件は記載されているが、12文字以上推奨に対して8文字と不十分。多要素認証は今後検討とされている。",
                "recommendation": "パスワード最低文字数を12文字以上に引き上げ、多要素認証を導入すること。",
            }
        elif "暗号化" in prompt or "暗号" in prompt:
            result = {
                "judgment": "warning",
                "evidence": "機密情報を含むデータの保存時には暗号化を実施する。通信時にはSSL/TLSを使用する。",
                "reason": "暗号化の実施は記載されているが、具体的なアルゴリズム（AES-256等）や暗号鍵管理手順が別途定めるとされ未整備。",
                "recommendation": "暗号化アルゴリズムの具体的指定と暗号鍵管理手順書の策定が必要。",
            }
        elif "アクセス制御" in prompt or "権限管理" in prompt:
            result = {
                "judgment": "pass",
                "evidence": "業務上必要な最小限の範囲で付与。退職者のアカウントは退職日当日に無効化。",
                "reason": "最小権限の原則に基づくアクセス制御と退職者アカウント管理が明記されている。",
                "recommendation": "",
            }
        elif "インシデント" in prompt:
            result = {
                "judgment": "pass",
                "evidence": "セキュリティインシデントを発見した場合は直ちに報告。原因分析と再発防止策を策定。",
                "reason": "インシデント報告・対応・再発防止の一連の手順が定められている。",
                "recommendation": "",
            }
        elif "個人情報" in prompt:
            result = {
                "judgment": "fail",
                "evidence": "個人情報：特定の個人を識別できる情報（第3条のみ）",
                "reason": "個人情報の定義はあるが、取得目的・利用範囲・第三者提供・委託先管理等の具体的な規定が欠如。",
                "recommendation": "個人情報保護に関する独立した章を設け、取得・利用・提供・委託の各段階での管理規定を追加すること。",
            }
        elif "ログ" in prompt:
            result = {
                "judgment": "fail",
                "evidence": "",
                "reason": "ログ管理に関する規定が文書内に見当たらない。",
                "recommendation": "アクセスログ・操作ログの取得、保存期間、定期的な監査について規定を追加すること。",
            }
        elif "事業継続" in prompt or "BCP" in prompt:
            result = {
                "judgment": "na",
                "evidence": "",
                "reason": "本文書は情報セキュリティポリシーであり、BCPは対象外。",
                "recommendation": "",
            }
        else:
            result = {
                "judgment": "na",
                "evidence": "",
                "reason": "本文書の対象範囲外の観点。",
                "recommendation": "",
            }
        return json.dumps(result, ensure_ascii=False)

    async def complete_json(self, prompt: str) -> dict:
        response = await self.complete(prompt)
        return json.loads(response)


# ---------------------------------------------------------------------------
# テスト実行
# ---------------------------------------------------------------------------
def test_e2e():
    print("=" * 60)
    print("E2E テスト開始")
    print("=" * 60)

    # 1. デフォルト審査観点ロード
    print("\n[1/6] デフォルト審査観点ロード...")
    criteria = load_defaults()
    print(f"  ✓ {len(criteria)} 項目ロード")
    assert len(criteria) == 27, f"Expected 27, got {len(criteria)}"

    df = criteria_to_dataframe(criteria)
    print(f"  ✓ DataFrame変換: {df.shape}")
    assert df.shape[0] == 27

    # 2. サンプルPDF解析
    print("\n[2/6] サンプルPDF解析...")
    pdf_path = str(Path(__file__).parent.parent / "examples" / "sample_policy.pdf")
    sections = extract_and_split(pdf_path)
    print(f"  ✓ {len(sections)} セクション抽出")
    for s in sections:
        print(f"    - {s.title[:40]}... ({len(s.content)} chars, pages={s.page_numbers})")
    assert len(sections) > 0, "No sections extracted"

    # 3. チャンク分割
    print("\n[3/6] チャンク分割...")
    chunks = chunk_sections(sections)
    print(f"  ✓ {len(chunks)} チャンク作成")
    for i, c in enumerate(chunks):
        print(f"    - chunk {i}: {len(c.text)} chars, {len(c.sections)} sections")
    assert len(chunks) > 0, "No chunks created"

    # 4. 審査実行（モックLLM）
    print("\n[4/6] 審査実行（モックLLM）...")
    client = MockLLMClient()

    progress_log = []

    def progress_cb(current, total):
        progress_log.append((current, total))

    results = asyncio.run(
        run_review(criteria, chunks, client, progress_callback=progress_cb)
    )
    print(f"  ✓ {len(results)} 件の審査結果")
    print(f"  ✓ LLM呼び出し回数: {client.call_count}")
    print(f"  ✓ 進捗コールバック: {len(progress_log)} 回")

    # 判定内訳
    stats = {}
    for r in results:
        stats[r.judgment] = stats.get(r.judgment, 0) + 1
    print(f"  判定内訳: {stats}")
    assert len(results) == 27, f"Expected 27 results, got {len(results)}"

    # 5. レポート生成
    print("\n[5/6] レポート生成...")
    md_report = generate_markdown_report(results, document_name="sample_policy")
    print(f"  ✓ Markdownレポート: {len(md_report)} chars")
    assert "# ガバナンス審査レポート" in md_report or "審査レポート" in md_report
    assert len(md_report) > 500

    html_report = generate_html_report(results, document_name="sample_policy")
    print(f"  ✓ HTMLレポート: {len(html_report)} chars")
    assert "<html" in html_report.lower() or "<!doctype" in html_report.lower()
    assert len(html_report) > 1000

    summary_df = generate_summary_dataframe(results)
    print(f"  ✓ サマリーDataFrame: {summary_df.shape}")
    assert summary_df.shape[0] == 27

    # 6. レポート保存テスト
    print("\n[6/6] レポート保存テスト...")
    import tempfile, os

    tmp_dir = tempfile.mkdtemp()
    md_path = os.path.join(tmp_dir, "test_report.md")
    html_path = os.path.join(tmp_dir, "test_report.html")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)

    print(f"  ✓ MD保存: {md_path} ({os.path.getsize(md_path)} bytes)")
    print(f"  ✓ HTML保存: {html_path} ({os.path.getsize(html_path)} bytes)")
    assert os.path.getsize(md_path) > 0
    assert os.path.getsize(html_path) > 0

    # サマリー出力
    print("\n" + "=" * 60)
    print("全テスト合格 ✓")
    print("=" * 60)
    print(f"\n--- Markdownレポート（冒頭500文字）---")
    print(md_report[:500])
    print("...")

    return True


if __name__ == "__main__":
    success = test_e2e()
    sys.exit(0 if success else 1)
