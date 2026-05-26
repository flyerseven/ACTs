import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from utils.logger import setup_logging
from storage.file_store import FileStore
from security.vault import Vault
from core.token_tracker import TokenTracker
from ui.main_window import MainWindow
from ui.styles import APP_STYLE

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

APP_VERSION = "0.1.0"


def _print_token_stats(tracker: TokenTracker, session_id: str = "") -> None:
    if session_id:
        stats = tracker.get_session_stats(session_id)
        print(f"Token usage for session {session_id}:")
    else:
        stats = tracker.get_total_stats()
        print("Total token usage:")

    print(f"  Requests:     {stats.total_requests}")
    print(f"  Prompt tokens:     {stats.total_prompt_tokens:,}")
    print(f"  Completion tokens: {stats.total_completion_tokens:,}")
    print(f"  Total tokens:      {stats.total_tokens:,}")
    if stats.total_cost > 0:
        print(f"  Est. cost:         ${stats.total_cost:.4f}")

    if stats.by_model:
        print("\n  By model:")
        for model, mstats in sorted(stats.by_model.items()):
            cost_str = f"  ${mstats['cost']:.4f}" if mstats["cost"] else ""
            print(f"    {model}: {mstats['requests']} req, {mstats['tokens']:,} tokens {cost_str}")

    recent = tracker.get_recent(5)
    if recent:
        print("\n  Recent requests:")
        for r in recent:
            cost_str = f"  ${r.cost:.4f}" if r.cost else ""
            print(f"    [{r.timestamp}] {r.model}: {r.prompt_tokens}+{r.completion_tokens}={r.total_tokens} tokens {cost_str}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ACTs - Agent Creat Tools")
    parser.add_argument("--health", action="store_true", help="Print health check and exit")
    parser.add_argument("--tokens", action="store_true", help="Print token usage stats and exit")
    parser.add_argument("--tokens-session", type=str, default="", metavar="SESSION_ID", help="Print token usage for a specific session")
    parser.add_argument("--tokens-clear", action="store_true", help="Clear all token usage records")
    args = parser.parse_args()

    if args.health:
        print("ACTs OK")
        return 0

    token_tracker = TokenTracker()

    if args.tokens_clear:
        token_tracker.clear()
        print("Token usage records cleared.")
        return 0

    if args.tokens or args.tokens_session:
        _print_token_stats(token_tracker, session_id=args.tokens_session)
        return 0

    setup_logging()
    store = FileStore()
    store.ensure_structure()

    vault = Vault(store.vault_path)
    vault.load()

    app = QApplication(sys.argv)
    app.setApplicationName("ACTs")
    app.setFont(QFont("IBM Plex Sans", 10))
    app.setStyleSheet(APP_STYLE)

    window = MainWindow(store=store, vault=vault, version=APP_VERSION, token_tracker=token_tracker)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
