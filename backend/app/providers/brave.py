import httpx

from app.config import settings
from app.providers.search_base import SearchProvider, SearchResult


class BraveProvider(SearchProvider):
    name = "brave"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        if not settings.brave_api_key:
            raise RuntimeError("BRAVE_API_KEY is required for SEARCH_PROVIDER=brave")
        with httpx.Client(timeout=30) as client:
            response = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": settings.brave_api_key,
                },
                params={"q": query, "count": max_results, "country": "KE"},
            )
            response.raise_for_status()
            data = response.json()
        items: list[SearchResult] = []
        for row in (data.get("web") or {}).get("results") or []:
            items.append(
                SearchResult(
                    title=row.get("title") or "",
                    url=row.get("url") or "",
                    snippet=row.get("description") or "",
                    source="brave",
                )
            )
        return items
