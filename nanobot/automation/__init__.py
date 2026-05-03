"""Automation domain helpers."""

from nanobot.automation.calendar import (
    CalendarAutomationSessionRunner,
    CalendarDeleteRequest,
    CalendarCreateRequest,
    CalendarUpdateRequest,
    N8NCalendarAutomationClient,
    N8NCalendarAutomationConfig,
)
from nanobot.automation.mail import (
    MailAutomationSessionRunner,
    MailDraftRequest,
    N8NGmailAutomationClient,
    N8NGmailAutomationConfig,
)

__all__ = [
    "CalendarAutomationSessionRunner",
    "CalendarCreateRequest",
    "CalendarDeleteRequest",
    "CalendarUpdateRequest",
    "N8NCalendarAutomationClient",
    "N8NCalendarAutomationConfig",
    "MailAutomationSessionRunner",
    "MailDraftRequest",
    "N8NGmailAutomationClient",
    "N8NGmailAutomationConfig",
]