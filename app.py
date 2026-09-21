"""
Bridge entrypoint for container and cloud hosting platforms
(e.g., Railway, Render, Coolify, Dokku, Cloud VPS) that default to `python app.py`.
"""

import asyncio
from main import main, logger

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
    except Exception as e:
        logger.exception("Fatal exception in bot runtime: %s", e)
