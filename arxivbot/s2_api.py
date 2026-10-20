"""Paper metadata from the Semantic Scholar batch endpoint."""

from __future__ import annotations

import logging
import threading
import time

import requests


LOGGER = logging.getLogger(__name__)

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_MAX_ATTEMPTS = 4
# S2 sends no Retry-After header on 429, so back off exponentially from this base
S2_BACKOFF_SECONDS = 2.0
# (connect, read) timeouts for one attempt
S2_TIMEOUT = (5, 20)
# No retry starts unless its backoff and a full attempt fit in this budget. Keeps the
# worst case near a minute, well inside the Telegram bot's 120s obsidian-import timeout.
S2_RETRY_BUDGET_SECONDS = 60.0


def fetch_s2_batch(
    paper_ids: list[str],
    fields: list[str],
    api_key: str | None = None,
    *,
    session: requests.Session | None = None,
) -> tuple[list[dict], list[str]]:
    """POST up to 500 IDs to /paper/batch. Returns (paper dicts, IDs S2 does not know).

    Retries rate limits (429), server errors, connection errors and timeouts with
    exponential backoff, within S2_MAX_ATTEMPTS and S2_RETRY_BUDGET_SECONDS. After
    that, raises requests.HTTPError for a bad status, or the last
    requests.ConnectionError / requests.Timeout.
    """
    http = session or requests
    headers = {"x-api-key": api_key} if api_key else {}
    deadline = time.monotonic() + S2_RETRY_BUDGET_SECONDS
    for attempt in range(1, S2_MAX_ATTEMPTS + 1):
        delay = S2_BACKOFF_SECONDS * 2 ** (attempt - 1)
        last_attempt = attempt == S2_MAX_ATTEMPTS
        try:
            response = _post_within(
                http,
                sum(S2_TIMEOUT),
                params={"fields": ",".join(fields)},
                json={"ids": paper_ids},
                headers=headers,
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            if last_attempt or time.monotonic() + delay + sum(S2_TIMEOUT) > deadline:
                raise
            problem = f"S2 request failed ({e})"
        else:
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or last_attempt or time.monotonic() + delay + sum(S2_TIMEOUT) > deadline:
                break
            problem = f"S2 returned HTTP {response.status_code}"
        LOGGER.warning(f"{problem}, retrying in {delay:.0f}s")
        time.sleep(delay)
    response.raise_for_status()

    # The response lists papers in request order, with null for unknown IDs
    results = response.json()
    papers = [paper for paper in results if paper is not None]
    not_found = [paper_id for paper_id, paper in zip(paper_ids, results, strict=True) if paper is None]
    return papers, not_found


def _post_within(http, seconds: float, **kwargs) -> requests.Response:
    """POST to the batch endpoint, raising requests.Timeout if it has not finished within `seconds`.

    requests' timeouts bound each socket wait, not the whole request, so headers or a
    body trickling in could otherwise outlast the retry budget. The request runs in a
    daemon thread, so an abandoned one cannot keep the process alive.
    """
    outcome: dict = {}

    def post() -> None:
        try:
            outcome["response"] = http.post(S2_BATCH_URL, timeout=S2_TIMEOUT, **kwargs)
        except Exception as e:
            outcome["error"] = e

    worker = threading.Thread(target=post, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise requests.Timeout(f"S2 request took longer than {seconds:.0f}s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["response"]
