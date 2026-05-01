"""Automation domain helpers."""

from nanobot.automation.calendar import (
    CalendarAutomationSessionRunner,
    CalendarCreateRequest,
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
    "N8NCalendarAutomationClient",
    "N8NCalendarAutomationConfig",
    "MailAutomationSessionRunner",
    "MailDraftRequest",
    "N8NGmailAutomationClient",
    "N8NGmailAutomationConfig",
]