"""Verdent Platform — RBAC (Document 3 §O; Phase 4).

Flat permission map per role — no implied hierarchy between SUPPORT and
INFRASTRUCTURE (they're different jobs, not ranks). OWNER implicitly holds
everything. New admin roles are additive: add a row to ROLE_PERMISSIONS.
"""

from db.models import Admin

ROLE_OWNER = "OWNER"
ROLE_ADMIN = "ADMIN"
ROLE_SUPPORT = "SUPPORT"
ROLE_FINANCE = "FINANCE"
ROLE_INFRASTRUCTURE = "INFRASTRUCTURE"

ALL_ROLES = [ROLE_OWNER, ROLE_ADMIN, ROLE_SUPPORT, ROLE_FINANCE, ROLE_INFRASTRUCTURE]

# Permissions
PERM_PAYMENT_REVIEW = "payment.review"          # approve/reject manual proofs
PERM_REFUND_MARK = "payment.refund"
PERM_CONFIG_MANAGE = "config.manage"            # revoke/suspend a customer's config
PERM_TEST_CONFIG = "config.test"                # issue test configs
PERM_PLAN_MANAGE = "plan.manage"
PERM_USER_BAN = "user.ban"
PERM_NODE_MANAGE = "node.manage"                # add/decommission nodes
PERM_GAMING_PROFILE = "gaming.manage"
PERM_ADMIN_MANAGE = "admin.manage"              # add/remove admins
PERM_STATS_VIEW = "stats.view"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_OWNER: {  # everything
        PERM_PAYMENT_REVIEW, PERM_REFUND_MARK, PERM_CONFIG_MANAGE, PERM_TEST_CONFIG,
        PERM_PLAN_MANAGE, PERM_USER_BAN, PERM_NODE_MANAGE, PERM_GAMING_PROFILE,
        PERM_ADMIN_MANAGE, PERM_STATS_VIEW,
    },
    ROLE_ADMIN: {
        PERM_PAYMENT_REVIEW, PERM_REFUND_MARK, PERM_CONFIG_MANAGE, PERM_TEST_CONFIG,
        PERM_PLAN_MANAGE, PERM_USER_BAN, PERM_NODE_MANAGE, PERM_GAMING_PROFILE,
        PERM_STATS_VIEW,
    },
    ROLE_SUPPORT: {
        PERM_PAYMENT_REVIEW, PERM_CONFIG_MANAGE, PERM_TEST_CONFIG, PERM_STATS_VIEW,
    },
    ROLE_FINANCE: {
        PERM_PAYMENT_REVIEW, PERM_REFUND_MARK, PERM_STATS_VIEW,
    },
    ROLE_INFRASTRUCTURE: {
        PERM_NODE_MANAGE, PERM_GAMING_PROFILE, PERM_STATS_VIEW,
    },
}


def permissions_for(role: str) -> set[str]:
    return ROLE_PERMISSIONS.get(role, set())


def role_has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def admin_role_for_telegram_id(telegram_user_id: int, admins: list[Admin]) -> str | None:
    # Admin.telegram_user_id is BIGINT — compare as int. A str comparison
    # never matches, which silently reports every admin as non-admin.
    for a in admins:
        if a.telegram_user_id == int(telegram_user_id):
            return a.role
    return None
