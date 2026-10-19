"""Explicit MySQL schema initialization, separate from ordinary server startup."""
import os
from backend.app.db import Store


def main():
    url = os.getenv('DATABASE_URL', '')
    if not url:
        print('DATABASE_URL is required.')
        return 1
    try:
        Store(database_url=url)
    except Exception:
        # Driver failures may contain hostnames and connection details.
        print('Schema initialization failed. Check private DB configuration and CREATE permissions.')
        return 1
    print('Storage tables initialized; existing table data was preserved.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
