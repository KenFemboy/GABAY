"""Application error type rendered in the shared error-response format.

Every error response has the shape ``{"error": {"code": ..., "message": ...}}``.
Raise ``APIError`` when the client needs a stable, machine-readable ``code``
(for example to tell an expired session apart from a missing permission).
"""


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        # Optional [{"field": ..., "message": ...}] list, same shape as validation errors.
        self.details = details


def not_authenticated(code: str = "not_authenticated", message: str = "Authentication is required.") -> APIError:
    return APIError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def forbidden(message: str = "You do not have permission to perform this action.") -> APIError:
    return APIError(403, "forbidden", message)


def not_found(message: str = "The requested resource was not found.") -> APIError:
    return APIError(404, "not_found", message)


def conflict(code: str, message: str) -> APIError:
    return APIError(409, code, message)
