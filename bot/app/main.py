"""Discord bot entrypoint — boots the discord.py client and syncs slash commands.

Syncs the /podcast command tree to the configured guild (fast propagation) or
globally when DISCORD_GUILD_ID is not set.
"""

import logging
import sys

import structlog

from app import commands, config

logger = structlog.get_logger(__name__)


def _configure_logging() -> None:
    """Configure structlog to emit JSON to stdout for the docker json-file driver."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def main() -> None:
    """Start the Discord bot.

    Registers the on_ready event to sync the command tree, then runs the
    client with the configured bot token.  Exits cleanly on KeyboardInterrupt.
    """
    _configure_logging()
    client = commands.get_client()
    tree = commands.get_tree()

    @client.event
    async def on_ready() -> None:
        """Sync command tree and log the ready state."""
        if config.DISCORD_GUILD_ID is not None:
            guild = client.get_guild(int(config.DISCORD_GUILD_ID))
            if guild is not None:
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
                logger.info(
                    "bot_ready_guild_sync",
                    guild_id=config.DISCORD_GUILD_ID,
                    user=str(client.user),
                )
            else:
                logger.warning(
                    "bot_ready_guild_not_found",
                    guild_id=config.DISCORD_GUILD_ID,
                )
                await tree.sync()
                logger.info("bot_ready_global_sync", user=str(client.user))
        else:
            await tree.sync()
            logger.info("bot_ready_global_sync", user=str(client.user))

    try:
        client.run(config.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("bot_shutdown_keyboard_interrupt")


if __name__ == "__main__":
    main()
