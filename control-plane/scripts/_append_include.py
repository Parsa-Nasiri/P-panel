"""One-off: append dispatcher include to bot/router.py."""

s = open("bot/router.py", encoding="utf-8").read()
if "_dp.include_router(router)" not in s:
    s += """

# include into the webhook dispatcher (module-level, AFTER all handlers register)
from bot.webhook import dp as _dp  # noqa: E402

_dp.include_router(router)
"""
    open("bot/router.py", "w", encoding="utf-8", newline="\n").write(s)
    print("appended")
else:
    print("already present")
