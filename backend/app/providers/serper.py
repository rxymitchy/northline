import httpx

from app.config import settings
from app.providers.search_base import SearchProvider, SearchResult


class SerperProvider(SearchProvider):
    name = "serper"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        if not settings.serper_api_key:
            raise RuntimeError("SERPER_API_KEY is required for SEARCH_PROVIDER=serper")
        with httpx.Client(timeout=30) as client:
            response = client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max_results, "gl": "ke"},
            )
            response.raise_for_status()
            data = response.json()
        items: list[SearchResult] = []
        for row in data.get("organic") or []:
            items.append(
                SearchResult(
                    title=row.get("title") or "",
                    url=row.get("link") or "",
                    snippet=row.get("snippet") or "",
                    source="serper",
                )
            )
        return items
