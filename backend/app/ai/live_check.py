"""Explicit opt-in live smoke test; no .env loading or credential output."""
import tempfile
from pathlib import Path
from uuid import uuid4
from backend.app.config import Settings
from backend.app.db.database import initialize
from backend.app.db.__main__ import seed_demo
from backend.app.services.support import SupportService
from .contracts import ChatRequest
from .gemini import GeminiModel
from .workflow import run


def main():
    settings = Settings()
    if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value():
        print('SKIPPED: GEMINI_API_KEY is not available in the process environment.')
        return
    with tempfile.TemporaryDirectory() as folder:
        settings = settings.model_copy(update={'database_path':Path(folder)/'live.sqlite3'})
        initialize(settings.database_path)
        seed_demo(settings.database_path)
        model = GeminiModel(settings)
        try:
            result = run(model, SupportService(settings), 1,
                ChatRequest(request_id=uuid4(), customer_id=1, message='Check the current status of order 1 using get_order, then give a brief answer.'), settings.agent_max_steps)
            assert result.status == 'completed'
            assert any(t.tool == 'get_order' and t.status == 'ok' for t in result.tools)
            print('PASS: live Gemini get_order tool call and structured final response verified.')
        finally:
            model.close()


if __name__ == '__main__':
    # Never expose provider exception text, HTTP headers, prompts or credentials.
    try:
        main()
    except Exception:
        print('FAILED: live workflow could not be verified; check configuration and service availability.')
        raise SystemExit(1) from None
