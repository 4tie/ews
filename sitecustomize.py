"""Optional runtime patches for subprocesses.

Why this exists:
- Freqtrade/ccxt uses aiohttp.
- On some Windows setups, aiodns/pycares can fail to contact DNS servers even when
  the system resolver works.

When `FT_FORCE_THREADED_RESOLVER=1` is set (we set this only for the freqtrade
subprocess), force aiohttp to use the threaded resolver.

NOTE: This mechanism has been disabled due to import failures during Python 3.12
initialization on Windows. If DNS issues occur, it will need to be revisited with
a deferred/lazy import approach.
"""

import os

# DISABLED: The environment variable trigger has been removed from freqtrade_cli_service.py
# due to Windows Python 3.12 initialization crashes. If needed, reimplement with deferred imports.
#
# if os.getenv("FT_FORCE_THREADED_RESOLVER") == "1":
#     try:
#         import aiohttp.connector
#         import aiohttp.resolver
#
#         aiohttp.resolver.DefaultResolver = aiohttp.resolver.ThreadedResolver
#         aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver
#     except Exception:
#         pass

