"""Machine-readable application errors."""


class AppError(Exception):
    code = "APP_ERROR"
    http_status = 400

    def __init__(self, message: str, *, code: str | None = None, details=None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}

    def as_dict(self) -> dict:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                **self.details,
            },
        }


class NotFoundError(AppError):
    code = "NOT_FOUND"
    http_status = 404


class AmbiguousPersonError(AppError):
    code = "PERSON_AMBIGUOUS"


class ValidationError(AppError):
    code = "VALIDATION_ERROR"


class ConflictError(AppError):
    code = "CONFLICT"
    http_status = 409


class JournalConflictError(ConflictError):
    code = "JOURNAL_CONFLICT"


class CycleError(ValidationError):
    code = "ANCESTRY_CYCLE"


class InvalidOperationError(AppError):
    code = "INVALID_OPERATION"
