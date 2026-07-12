"""API key scope constants (story A3)."""
from api.models import UserRole

VALID_SCOPES = frozenset(
    {
        "jobs:read",
        "jobs:write",
        "models:read",
        "llm:invoke",
        "instances:manage",
    }
)

ROLE_SCOPES: dict[UserRole, frozenset[str]] = {
    UserRole.admin: VALID_SCOPES,
    UserRole.user: VALID_SCOPES,
    UserRole.readonly: frozenset({"jobs:read", "models:read"}),
}


def scopes_allowed_for_role(role: UserRole, requested: list[str]) -> bool:
    allowed = ROLE_SCOPES[role]
    return all(scope in allowed for scope in requested)
