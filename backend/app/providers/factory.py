from app.config import settings
from app.providers.brave import BraveProvider
from app.providers.duckduckgo import DuckDuckGoProvider
from app.providers.search_base import SearchProvider
from app.providers.serper import SerperProvider
from app.providers.tavily import TavilyProvider


PROVIDERS = {
    "duckduckgo": DuckDuckGoProvider,
    "tavily": TavilyProvider,
    "serper": SerperProvider,
    "brave": BraveProvider,
}


def get_search_provider(name: str | None = None) -> SearchProvider:
    key = (name or settings.search_provider or "duckduckgo").lower().strip()
    if key not in PROVIDERS:
        raise ValueError(f"Unknown SEARCH_PROVIDER '{key}'. Use: {', '.join(PROVIDERS)}")
    return PROVIDERS[key]()


def get_web_search_provider() -> SearchProvider:
    """Prefer a keyed engine when present — stronger for social/website mentions."""
    if settings.serper_api_key:
        return SerperProvider()
    if settings.brave_api_key:
        return BraveProvider()
    if settings.tavily_api_key:
        return TavilyProvider()
    return get_search_provider()
