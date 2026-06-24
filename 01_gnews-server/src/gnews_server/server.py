"""FastMCP server exposing the GNews API as MCP tools.

Two tools are exposed, one per GNews endpoint:

* ``search_news``    -> https://gnews.io/api/v4/search
* ``top_headlines``  -> https://gnews.io/api/v4/top-headlines

The GNews API key is read from the ``GNEWS_API_KEY`` environment variable.
Get one at https://gnews.io/.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

GNEWS_BASE_URL = "https://gnews.io/api/v4"
API_KEY_ENV = "GNEWS_API_KEY"

mcp = FastMCP("gnews")


def _api_key() -> str:
    """Return the configured GNews API key or raise a helpful error."""
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise ValueError(
            f"Missing GNews API key. Set the {API_KEY_ENV} environment variable. "
            "Get a key at https://gnews.io/."
        )
    return key


async def _request(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call a GNews endpoint, dropping unset (``None``) parameters."""
    query = {k: v for k, v in params.items() if v is not None}
    query["apikey"] = _api_key()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{GNEWS_BASE_URL}/{endpoint}", params=query)

    if response.status_code != httpx.codes.OK:
        # GNews returns an "errors" array describing what went wrong.
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"GNews API request failed (HTTP {response.status_code}): {detail}"
        )

    return response.json()


@mcp.tool()
async def search_news(
    q: Annotated[
        str,
        Field(
            description=(
                "Search keywords (max 200 chars). Supports logical operators: "
                'phrases in quotes ("exact phrase"), AND, OR, NOT.'
            ),
            max_length=200,
        ),
    ],
    lang: Annotated[
        str | None,
        Field(description="2-letter language code, e.g. 'en', 'fr'."),
    ] = None,
    country: Annotated[
        str | None,
        Field(description="2-letter country code of publication, e.g. 'us', 'gb'."),
    ] = None,
    max: Annotated[
        int,
        Field(description="Number of articles to return (1-100).", ge=1, le=100),
    ] = 10,
    in_: Annotated[
        str | None,
        Field(
            description=(
                "Maps to the GNews 'in' parameter. Comma-separated attributes to "
                "search within: title, description, content. Defaults to 'title,description'."
            ),
        ),
    ] = None,
    nullable: Annotated[
        str | None,
        Field(
            description=(
                "Comma-separated attributes allowed to be null in results: "
                "description, content, image."
            )
        ),
    ] = None,
    from_: Annotated[
        str | None,
        Field(
            description=(
                "Maps to the GNews 'from' parameter. Minimum publication date, "
                "ISO 8601 (e.g. 2024-01-01T00:00:00Z)."
            ),
        ),
    ] = None,
    to: Annotated[
        str | None,
        Field(description="Maximum publication date, ISO 8601 (e.g. 2024-12-31T23:59:59Z)."),
    ] = None,
    sortby: Annotated[
        Literal["publishedAt", "relevance"],
        Field(description="Sort order of the results."),
    ] = "publishedAt",
    page: Annotated[
        int,
        Field(description="Page number for pagination (max 1000 articles total).", ge=1),
    ] = 1,
    truncate: Annotated[
        bool,
        Field(description="If true, truncate the article 'content' field."),
    ] = False,
) -> dict[str, Any]:
    """Search worldwide news articles matching keywords via the GNews search endpoint.

    Returns a dict with ``totalArticles`` and an ``articles`` list. Each article
    has: id, title, description, content, url, image, publishedAt, lang, and a
    ``source`` object (id, name, url, country).
    """
    params = {
        "q": q,
        "lang": lang,
        "country": country,
        "max": max,
        "in": in_,
        "nullable": nullable,
        "from": from_,
        "to": to,
        "sortby": sortby,
        "page": page,
        "truncate": "content" if truncate else None,
    }
    return await _request("search", params)


@mcp.tool()
async def top_headlines(
    category: Annotated[
        Literal[
            "general",
            "world",
            "nation",
            "business",
            "technology",
            "entertainment",
            "sports",
            "science",
            "health",
        ],
        Field(description="News category to fetch headlines for."),
    ] = "general",
    lang: Annotated[
        str | None,
        Field(description="2-letter language code, e.g. 'en', 'fr'."),
    ] = None,
    country: Annotated[
        str | None,
        Field(description="2-letter country code, e.g. 'us', 'gb'."),
    ] = None,
    max: Annotated[
        int,
        Field(description="Number of articles to return (1-100).", ge=1, le=100),
    ] = 10,
    q: Annotated[
        str | None,
        Field(
            description="Optional search keywords (max 200 chars). Supports logical operators.",
            max_length=200,
        ),
    ] = None,
    nullable: Annotated[
        str | None,
        Field(
            description=(
                "Comma-separated attributes allowed to be null: "
                "description, content, image."
            )
        ),
    ] = None,
    from_: Annotated[
        str | None,
        Field(
            description=(
                "Maps to the GNews 'from' parameter. Minimum publication date, "
                "ISO 8601 (e.g. 2024-01-01T00:00:00Z)."
            ),
        ),
    ] = None,
    to: Annotated[
        str | None,
        Field(description="Maximum publication date, ISO 8601 (e.g. 2024-12-31T23:59:59Z)."),
    ] = None,
    page: Annotated[
        int,
        Field(description="Page number for pagination (max 1000 articles total).", ge=1),
    ] = 1,
    truncate: Annotated[
        bool,
        Field(description="If true, truncate the article 'content' field."),
    ] = False,
) -> dict[str, Any]:
    """Fetch top breaking-news headlines by category via the GNews top-headlines endpoint.

    Returns a dict with ``totalArticles`` and an ``articles`` list. Each article
    has: id, title, description, content, url, image, publishedAt, lang, and a
    ``source`` object (id, name, url, country).
    """
    params = {
        "category": category,
        "lang": lang,
        "country": country,
        "max": max,
        "q": q,
        "nullable": nullable,
        "from": from_,
        "to": to,
        "page": page,
        "truncate": "content" if truncate else None,
    }
    return await _request("top-headlines", params)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
