from app.config import Settings
from app.memory import session_memory


def test_is_configured_false_when_keys_missing():
    settings = Settings(anthropic_api_key="", voyage_api_key="")
    assert session_memory.is_configured(settings) is False


def test_is_configured_true_when_both_keys_present_and_enabled():
    settings = Settings(anthropic_api_key="ant-key", voyage_api_key="voy-key", memory_enabled=True)
    assert session_memory.is_configured(settings) is True


def test_is_configured_false_when_only_one_key_present():
    settings = Settings(anthropic_api_key="ant-key", voyage_api_key="", memory_enabled=True)
    assert session_memory.is_configured(settings) is False


def test_is_configured_false_when_keys_present_but_kill_switch_off():
    # Found live: mem0's installed version is incompatible with the installed
    # anthropic SDK (TypeError on every call) — memory_enabled is a separate
    # kill-switch from key presence so this can be disabled without touching
    # real credentials, until the upstream version mismatch is fixed.
    settings = Settings(anthropic_api_key="ant-key", voyage_api_key="voy-key", memory_enabled=False)
    assert session_memory.is_configured(settings) is False


def test_safe_recall_no_ops_without_network_when_unconfigured():
    # No keys set in the test environment's default Settings() — this must
    # return instantly with no attempted network call, not raise or hang.
    result = session_memory.safe_recall("sess-1", "what did they say about pricing")
    assert result == []


def test_safe_recall_no_ops_on_empty_query():
    result = session_memory.safe_recall("sess-1", "   ")
    assert result == []


def test_safe_write_back_no_ops_without_network_when_unconfigured():
    # Must not raise even though mem0/Voyage/Anthropic aren't configured.
    session_memory.safe_write_back("sess-1", "hello", "hi there")
