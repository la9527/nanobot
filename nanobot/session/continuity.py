"""Minimal single-user continuity metadata helpers.

This phase intentionally keeps continuity lightweight: a stable canonical
owner plus per-session channel identity hints that can be reused by WebUI,
approval visibility, and later domain integrations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PRIMARY_OWNER_ID = "primary-user"
CONTINUITY_METADATA_KEY = "continuity"


def _channel_kind(session_key: str) -> str:
    prefix, _, _rest = session_key.partition(":")
    return prefix or "unknown"


def _external_identity(session_key: str) -> str:
    channel, _, remainder = session_key.partition(":")
    if channel == "websocket":
        return "local-webui"
    if not remainder:
        return session_key
    return remainder.split(":thread:", 1)[0].split(":topic:", 1)[0]


def _default_trust_level(channel_kind: str) -> str:
    if channel_kind == "websocket":
        return "trusted"
    return "linked"


def normalized_session_metadata(
    session_key: str,
    metadata: dict[str, Any] | None,
    *,
    last_confirmed_at: str | None,
) -> dict[str, Any]:
    """Return a metadata dict with the minimum continuity block present.

    Existing continuity fields win when already present so future explicit
    linking or higher-trust flows can override these defaults without fighting
    the normalizer.
    """
    base = deepcopy(metadata) if isinstance(metadata, dict) else {}
    continuity = base.get(CONTINUITY_METADATA_KEY)
    continuity_dict = dict(continuity) if isinstance(continuity, dict) else {}

    channel_kind = continuity_dict.get("channel_kind")
    if not isinstance(channel_kind, str) or not channel_kind.strip():
        channel_kind = _channel_kind(session_key)

    external_identity = continuity_dict.get("external_identity")
    if not isinstance(external_identity, str) or not external_identity.strip():
        external_identity = _external_identity(session_key)

    canonical_owner_id = continuity_dict.get("canonical_owner_id")
    if not isinstance(canonical_owner_id, str) or not canonical_owner_id.strip():
        canonical_owner_id = PRIMARY_OWNER_ID

    trust_level = continuity_dict.get("trust_level")
    if not isinstance(trust_level, str) or not trust_level.strip():
        trust_level = _default_trust_level(channel_kind)

    confirmed = continuity_dict.get("last_confirmed_at")
    if not isinstance(confirmed, str) or not confirmed.strip():
        confirmed = last_confirmed_at

    base[CONTINUITY_METADATA_KEY] = {
        "canonical_owner_id": canonical_owner_id,
        "channel_kind": channel_kind,
        "external_identity": external_identity,
        "trust_level": trust_level,
        "last_confirmed_at": confirmed,
    }
    return base
