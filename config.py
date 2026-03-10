"""アプリケーション設定"""

import os

# LLM設定
DEFAULT_MODEL = os.getenv("GOVERNANCE_LLM_MODEL", "claude-sonnet-4-20250514")

AVAILABLE_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
    "gpt-4o",
    "gpt-4o-mini",
]

# 審査設定
MAX_CHUNK_TOKENS = 8000
CHUNK_OVERLAP_TOKENS = 500

# 判定ラベル
JUDGMENTS = {
    "pass": "✅ 適合",
    "warning": "⚠️ 要確認",
    "fail": "❌ 不適合",
    "na": "➖ 該当なし",
}

SEVERITY_LABELS = {
    "high": "🔴 高",
    "medium": "🟡 中",
    "low": "🟢 低",
}
