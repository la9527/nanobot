"""Heartbeat proactive delivery helpers.

The legacy HeartbeatService scheduling mechanism was replaced upstream by
cron-based auto-registration (see Task 13 in the upgrade plan). This package
currently exposes only the pure proactive-delivery policy/decision helpers in
``proactive.py``; cron wiring is added separately.
"""
