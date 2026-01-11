#!/usr/bin/env python3
"""
TRC - The Riven Companion

A monitoring tool that automatically fixes failed and stalled items in Riven
by leveraging Real-Debrid for torrent management.

Usage:
    python -m src.main

Environment Variables:
    RIVEN_URL           - Riven API URL (default: http://localhost:8083)
    RIVEN_API_KEY       - Riven API key (required)
    RD_API_KEY          - Real-Debrid API key (required)
    CHECK_INTERVAL_HOURS - Hours between checks (default: 6)
    RETRY_INTERVAL_MINUTES - Minutes between retries (default: 10)
    RD_CHECK_INTERVAL_MINUTES - Minutes between RD status checks (default: 5)
    RD_MAX_WAIT_HOURS   - Max hours to wait for RD download (default: 2)
    MAX_RIVEN_RETRIES   - Max Riven retries before manual scrape (default: 3)
    MAX_RD_TORRENTS     - Max torrents to try per item (default: 10)
    MAX_ACTIVE_RD_DOWNLOADS - Max concurrent RD downloads (default: 3)
    TORRENT_ADD_DELAY_SECONDS - Delay between adding torrents (default: 30)
    LOG_LEVEL           - Logging level (default: INFO)
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

from .config import load_config
from .rate_limiter import RateLimiterManager
from .riven_client import RivenClient
from .rd_client import RealDebridClient
from .monitor import TRCMonitor

# Global state for signal handling
_monitor: TRCMonitor = None
_shutdown_requested = False


def setup_logging(level: str):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def request_shutdown():
    """Request a graceful shutdown."""
    global _shutdown_requested
    logger = logging.getLogger(__name__)

    if _shutdown_requested:
        logger.warning("Shutdown already requested, forcing exit...")
        sys.exit(1)

    _shutdown_requested = True
    logger.info("Shutdown requested...")

    if _monitor:
        # Schedule the stop coroutine in the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_monitor.stop())
        except RuntimeError:
            # No running loop, just set the flag
            pass


async def main():
    """Main entry point."""
    global _monitor
    
    # Load configuration
    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease set the required environment variables:")
        print("  RIVEN_API_KEY - Your Riven API key")
        print("  RD_API_KEY    - Your Real-Debrid API key")
        sys.exit(1)
    
    # Setup logging
    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)
    
    # Print banner (ASCII-safe for Windows compatibility)
    print("""
+-----------------------------------------------------------+
|           TRC - The Riven Companion v1.0.0                |
|                                                           |
|  Automatically fixes failed and stalled items in Riven    |
+-----------------------------------------------------------+
    """)
    
    logger.info("Starting TRC - The Riven Companion")
    logger.info(f"Riven URL: {config.riven_url}")
    logger.info(f"Check interval: {config.check_interval_hours} hours")
    logger.info(f"Max Riven retries: {config.max_riven_retries}")
    logger.info(f"Max active RD downloads: {config.max_active_rd_downloads}")
    if config.skip_riven_retry:
        logger.info("SKIP_RIVEN_RETRY=true: Skipping remove+add, going directly to manual scrape")
    
    # Setup rate limiters
    rate_limiter = RateLimiterManager()
    rate_limiter.register("riven", config.riven_rate_limit_seconds)
    rate_limiter.register("rd", config.rd_rate_limit_seconds)
    
    # Create clients
    riven = RivenClient(config, rate_limiter)
    rd = RealDebridClient(config, rate_limiter)
    
    # Create monitor
    _monitor = TRCMonitor(config, riven, rd)

    # Setup signal handlers - use loop.add_signal_handler on Unix, signal.signal on Windows
    loop = asyncio.get_running_loop()

    if sys.platform != "win32":
        # Unix-style signal handling
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, request_shutdown)
    else:
        # Windows-style signal handling
        def signal_handler(sig, frame):
            request_shutdown()
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        await _monitor.start()
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        await riven.close()
        await rd.close()
        logger.info("TRC shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

