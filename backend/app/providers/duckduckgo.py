from concurrent.futures import ThreadPoolExecutor

from app.providers.search_base import SearchProvider, SearchResult


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        # One region only — a second pass was doubling wait time on diagnosis.
        return self._query(query, max_results, "wt-wt")[:max_results]

    def _query(self, query: str, max_results: int, region: str) -> list[SearchResult]:
        from ddgs import DDGS

        def run() -> list[SearchResult]:
            found: list[SearchResult] = []
            try:
                with DDGS() as ddgs:
                    for row in ddgs.text(query, region=region, max_results=max_results):
                        found.append(
                            SearchResult(
                                title=row.get("title") or "",
                                url=row.get("href") or row.get("url") or "",
                                snippet=row.get("body") or row.get("snippet") or "",
                                source="duckduckgo",
                            )
                        )
            except Exception:
                return found
            return found

        pool = ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(run).result(timeout=6)
        except Exception:
            return []
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
