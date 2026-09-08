from app.providers.search_base import SearchProvider, SearchResult


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        from ddgs import DDGS

        items: list[SearchResult] = []
        with DDGS() as ddgs:
            for row in ddgs.text(query, max_results=max_results):
                items.append(
                    SearchResult(
                        title=row.get("title") or "",
                        url=row.get("href") or row.get("url") or "",
                        snippet=row.get("body") or row.get("snippet") or "",
                        source="duckduckgo",
                    )
                )
        return items
