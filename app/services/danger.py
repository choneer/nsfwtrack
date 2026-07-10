from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.settings import AppSettings, get_app_settings

STRICT_CONFIRMATION_TEXT = "CONFIRM"


@dataclass(frozen=True)
class DangerPolicy:
    confirmation_mode: str = "standard"
    backup_reminder_mode: str = "dangerous_only"
    result_detail: str = "detailed"

    @property
    def is_strict(self) -> bool:
        return self.confirmation_mode == "strict"

    @property
    def show_detailed_results(self) -> bool:
        return self.result_detail == "detailed"

    def show_backup_reminder(self, backup_recommended: bool) -> bool:
        return self.backup_reminder_mode == "always" or backup_recommended


class DangerConfirmationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def danger_policy_from_settings(settings: AppSettings) -> DangerPolicy:
    return DangerPolicy(
        confirmation_mode=settings.danger_confirmation_mode,
        backup_reminder_mode=settings.backup_reminder_mode,
        result_detail=settings.danger_result_detail,
    )


def get_danger_policy(db: Session | None) -> DangerPolicy:
    if db is None:
        return DangerPolicy()
    try:
        settings = get_app_settings(db)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return DangerPolicy()
    return danger_policy_from_settings(settings)


def require_danger_confirmation(
    policy: DangerPolicy,
    *,
    confirmation_text: str | None,
    base_confirmation_valid: bool = True,
) -> None:
    if not base_confirmation_valid:
        raise DangerConfirmationError("confirm_required")
    if policy.is_strict and confirmation_text != STRICT_CONFIRMATION_TEXT:
        raise DangerConfirmationError("strict_text_required")
