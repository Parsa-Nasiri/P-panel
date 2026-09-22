"""Verdent Platform — display-name rules + unique suffix minting.

Document 1 §D: what must be unique, forever, is the full displayed string
`{display_name}_{suffix}`. The customer picks display_name (≤20 chars,
letters/digits — Persian or Latin); the suffix is a random CHAR(5) minted by
the platform. Collision → re-mint (the customer keeps their chosen name).
"""

import secrets
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Configuration

NAME_MAX_LEN = 20
_SUFFIX_ALPHABET = string.ascii_uppercase + string.digits  # 36^5 ≈ 60M combos


def validate_display_name(name: str) -> bool:
    """≤20 chars, letters (any script) and digits only, no spaces/punct."""
    name = name.strip()
    if not name or len(name) > NAME_MAX_LEN:
        return False
    return all(ch.isalnum() for ch in name)


def mint_suffix() -> str:
    return "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(5))


async def create_unique_config_name_pair(
    db: AsyncSession, display_name: str
) -> tuple[str, str]:
    """Return (display_name, suffix) with a suffix collision-checked against
    the (display_name, suffix) unique index. Retries on the astronomically
    unlikely duplicate."""
    display_name = display_name.strip()

    for _ in range(10):
        suffix = mint_suffix()
        exists = (
            await db.execute(
                select(Configuration.id).where(
                    Configuration.display_name == display_name,
                    Configuration.suffix == suffix,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            return display_name, suffix

    raise RuntimeError("could not mint a unique suffix after 10 tries")
