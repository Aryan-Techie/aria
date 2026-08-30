from unittest.mock import patch

from app.config import Settings
from app.rtm.publisher import (
    AgoraRtmPublisher,
    CompositePublisher,
    LoggingPublisher,
    SessionEventRecorder,
    default_rtm_publisher,
)


def test_default_rtm_publisher_falls_back_to_logging_when_unconfigured():
    settings = Settings(agora_app_id="", agora_customer_key="", agora_customer_secret="")
    with patch("app.config.get_settings", return_value=settings):
        publisher = default_rtm_publisher()
    assert isinstance(publisher, LoggingPublisher)


def test_default_rtm_publisher_fans_out_to_recorder_and_agora_when_configured():
    """Configured, events go to BOTH the session recorder (which the browser
    polls over HTTP) and Agora RTM."""
    settings = Settings(agora_app_id="app123", agora_customer_key="key123", agora_customer_secret="secret123")
    with patch("app.config.get_settings", return_value=settings):
        publisher = default_rtm_publisher()

    assert isinstance(publisher, CompositePublisher)
    kinds = [type(p) for p in publisher._publishers]
    assert SessionEventRecorder in kinds
    assert AgoraRtmPublisher in kinds


def test_composite_publisher_continues_after_one_member_raises():
    class Exploding:
        def publish(self, session_id, event_type, payload):
            raise RuntimeError("boom")

    received = []

    class Recording:
        def publish(self, session_id, event_type, payload):
            received.append((session_id, event_type))

    CompositePublisher(Exploding(), Recording()).publish("sess-1", "qualification_updated", {})
    assert received == [("sess-1", "qualification_updated")]


def test_agora_rtm_publisher_posts_to_correct_url_and_swallows_errors():
    publisher = AgoraRtmPublisher("app123", "key123", "secret123")

    # The real publish hands the POST to a background thread so a live call
    # never waits on it; run it inline here so the assertions are deterministic
    # rather than racing the pool.
    def run_inline(fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception:
            pass

    with (
        patch("app.rtm.publisher.httpx.post") as mock_post,
        patch("app.rtm.publisher.run_in_background", run_inline),
    ):
        mock_post.side_effect = Exception("network error")
        # must not raise even though the POST fails — RTM events are best-effort
        publisher.publish("sess-1", "qualification_updated", {"company": "Acme"})

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.agora.io/dev/v2/project/app123/rtm/users/aria-backend/channel_messages"
    assert kwargs["json"]["channel_name"] == "sess-1"  # falls back to session_id when no session/channel found
