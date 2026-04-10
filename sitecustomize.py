"""Optional runtime patches for subprocesses.

Why this exists:
- Freqtrade/ccxt uses aiohttp.
- On some Windows setups, aiodns/pycares can fail to contact DNS servers even when
  the system resolver works.

When `FT_FORCE_THREADED_RESOLVER=1` is set (we set this only for the freqtrade
subprocess), force aiohttp to use the threaded resolver.
"""

import os


if os.getenv("FT_FORCE_THREADED_RESOLVER") == "1":
    try:
        import aiohttp.connector
        import aiohttp.resolver

        aiohttp.resolver.DefaultResolver = aiohttp.resolver.ThreadedResolver
        aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver
    except Exception:
        pass
