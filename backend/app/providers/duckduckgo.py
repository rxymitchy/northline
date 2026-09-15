import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from app.providers.search_base import SearchProvider, SearchResult


_STOP = {
    "official",
    "website",
    "company",
    "kenya",
    "nairobi",
    "best",
    "top",
    "site",
    "sites",
    "similar",
    "companies",
}
_NOISE_HOSTS = (
    "youtube.com",
    "youtu.be",
    "pinkbike.com",
    "tiktok.com",
    "support.google.com",
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "pinterest.com",
    "x.com",
    "twitter.com",
    "maps.google.com",
)


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        collected: list[SearchResult] = []
        seen: set[str] = set()
        for backend in ("html", "lite", "auto"):
            for row in self._query(query, max_results, backend):
                url = (row.url or "").strip()
                if not url.startswith("http") or url in seen:
                    continue
                if not self._useful(query, row):
                    continue
                seen.add(url)
                collected.append(row)
            if len(collected) >= max(3, min(max_results, 6)):
                break
        return collected[:max_results]

    def _useful(self, query: str, row: SearchResult) -> bool:
        host = urlparse(row.url or "").netloc.lower().replace("www.", "")
        if any(host == n or host.endswith("." + n) for n in _NOISE_HOSTS):
            return False
        tokens = [t for t in re.findall(r"[a-z0-9]{4,}", (query or "").lower()) if t not in _STOP]
        if not tokens:
            return True
        blob = f"{row.title} {row.url} {row.snippet}".lower()
        return any(t in blob for t in tokens)

    def _query(self, query: str, max_results: int, backend: str) -> list[SearchResult]:
        from ddgs import DDGS

        def run() -> list[SearchResult]:
            found: list[SearchResult] = []
            try:
                with DDGS() as ddgs:
                    for row in ddgs.text(query, region="wt-wt", max_results=max_results, backend=backend):
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
            return pool.submit(run).result(timeout=8)
        except Exception:
            return []
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
