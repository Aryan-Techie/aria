"""RTC/RTM token generation for the browser client's join credentials.
Requires AGORA_APP_ID + AGORA_APP_CERTIFICATE — see .env.example."""
import time

from agora_token_builder import RtcTokenBuilder, RtmTokenBuilder
from agora_token_builder.RtcTokenBuilder import Role_Publisher

TOKEN_TTL_SECONDS = 3600  # generous for a demo call; not meant for long-lived production sessions


def build_rtc_token(app_id: str, app_certificate: str, channel_name: str, uid: int) -> str:
    expire_at = int(time.time()) + TOKEN_TTL_SECONDS
    return RtcTokenBuilder.buildTokenWithUid(
        app_id, app_certificate, channel_name, uid, Role_Publisher, expire_at
    )


def build_rtm_token(app_id: str, app_certificate: str, user_account: str) -> str:
    expire_at = int(time.time()) + TOKEN_TTL_SECONDS
    return RtmTokenBuilder.buildToken(app_id, app_certificate, user_account, 1, expire_at)
