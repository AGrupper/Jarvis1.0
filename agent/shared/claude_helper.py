"""Wrapper around the Anthropic SDK for AI summarization."""

import logging

from anthropic import Anthropic, APIError

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024


def get_client() -> Anthropic:
    """Return an Anthropic client (reads ANTHROPIC_API_KEY from env)."""
    return Anthropic()


def summarize(
    content: str,
    system_prompt: str,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Send content to Claude for summarization.

    Args:
        content: The raw text to summarize.
        system_prompt: Instructions for Claude's role and output format.
        max_tokens: Maximum response length.

    Returns:
        The text content of Claude's response.
    """
    client = get_client()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text
    except APIError as e:
        logger.error("Claude API error: %s", e)
        raise
