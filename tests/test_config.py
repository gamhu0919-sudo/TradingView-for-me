import os

import pytest

from bot.__main__ import acquire_single_instance_lock
from bot.config import Settings, load_dotenv


def test_dotenv_tolerates_bom_and_quotes(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_bytes("﻿TELEGRAM_BOT_TOKEN=abc:123\nTELEGRAM_CHAT_ID='42'\n# 주석\nLOG_FILE=data/bot.log\n".encode())
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LOG_FILE"):
        monkeypatch.delenv(key, raising=False)
    load_dotenv(env)
    settings = Settings.from_env()
    assert settings.bot_token == "abc:123"
    assert settings.chat_id == 42
    assert str(settings.log_file).replace(os.sep, "/") == "data/bot.log"


def test_single_instance_lock(tmp_path):
    first = acquire_single_instance_lock(tmp_path / "bot.lock")
    with pytest.raises(RuntimeError):
        acquire_single_instance_lock(tmp_path / "bot.lock")
    first.close()
    acquire_single_instance_lock(tmp_path / "bot.lock").close()  # 해제 후 다시 잡을 수 있음
