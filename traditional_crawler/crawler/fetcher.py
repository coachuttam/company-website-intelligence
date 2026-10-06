import time

import httpx


def fetch_page(
    url: str,
    retries: int = 3,
    retry_delay: float = 2.0
) -> str:

    for attempt in range(retries + 1):

        try:
            response = httpx.get(
                url,
                timeout=10,
                follow_redirects=True
            )

            response.raise_for_status()

            return response.text

        except httpx.RequestError as error:

            if attempt == retries:
                raise error

            print(
                f"Request failed: {url} "
                f"| Attempt {attempt + 1}/{retries + 1}"
            )

            time.sleep(retry_delay)