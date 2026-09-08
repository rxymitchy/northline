import httpx

from app.config import settings
from app.providers.search_base import SearchProvider, SearchResult


class TavilyProvider(SearchProvider):
    name = "tavily"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is required for SEARCH_PROVIDER=tavily")
        with httpx.Client(timeout=30) as client:
            response = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": False,
                },
            )
            response.raise_for_status()
            data = response.json()
        items: list[SearchResult] = []
        for row in data.get("results") or []:
            items.append(
                SearchResult(
                    title=row.get("title") or "",
                    url=row.get("url") or "",
                    snippet=row.get("content") or "",
                    source="tavily",
                )
            )
        return items
