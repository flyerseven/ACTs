import sys
from pathlib import Path

# Add project root's src/ directory to sys.path so that
# agent_engine modules can import from 'llm.base', etc.
_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
