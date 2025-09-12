import logging
import time
from functools import wraps
from typing import Any, Callable, Generator, Optional


def paginated_data(
    page_size: int = 100,
    max_pages: Optional[int] = None,
    max_records: Optional[int] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
):
    """
    Decorator that transforms a single-page fetching function into a generator
    that handles pagination automatically, with safeguards for memory usage.
    """
    def decorator(fetch_func: Callable[..., Any]) -> Callable[..., Generator[Any, None, None]]:
        @wraps(fetch_func)
        def wrapper(*args, **kwargs):
            """
            Wraps a function that fetches a single page of data and transforms it
            into a generator that handles pagination with proper error handling.
            """
            logging.info(f"Beginning paginated fetch with page_size={page_size}")

            current_page = 1
            records_fetched = 0
            pages_fetched = 0

            # Remove pagination-specific kwargs so they don't get passed to the wrapped function
            kwargs.pop('page', None)
            kwargs.pop('page_size', None)

            while True:
                # Handle retries for network/service failures
                retries = 0
                page_data = None
                while retries <= max_retries:
                    try:
                        # Call the original function to fetch a single page
                        page_data = fetch_func(
                            page=current_page, page_size=page_size, *args, **kwargs
                        )
                        break
                    except Exception as e:
                        retries += 1
                        logging.warning(
                            f"Fetch error on page {current_page} (attempt {retries}/{max_retries}): {e}"
                        )
                        if retries >= max_retries:
                            logging.error(
                                f"Failed to fetch page {current_page} after {max_retries} retries"
                            )
                            # In a generator, we return to stop iteration
                            return
                        time.sleep(retry_delay)

                # Circuit breaker: no more data
                if not page_data:
                    logging.info(f"No more data available after page {current_page-1}. Stopping.")
                    break

                # Yield the page data
                yield page_data

                # Update counters
                page_size_actual = (
                    len(page_data) if hasattr(page_data, "__len__") else 0
                )
                if page_size_actual == 0:
                    logging.info(f"Empty page returned on page {current_page}. Stopping.")
                    break


                records_fetched += page_size_actual
                pages_fetched += 1

                # Circuit breaker: max records limit
                if max_records and records_fetched >= max_records:
                    logging.info(f"Reached max records limit ({max_records})")
                    break

                # Circuit breaker: max pages limit
                if max_pages and pages_fetched >= max_pages:
                    logging.info(f"Reached max pages limit ({max_pages})")
                    break

                # Move to the next page
                current_page += 1

            logging.info(
                f"Pagination complete: {records_fetched} records across {pages_fetched} pages"
            )

        return wrapper
    return decorator