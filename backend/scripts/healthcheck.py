"""Container readiness check; session/team secrets are never printed."""
import os
from pathlib import Path
import urllib.request


def main():
    try:
        headers = {}
        if os.getenv('TEAM_SHARED_MODE', 'false').lower() == 'true':
            headers['X-Team-Key'] = Path(os.environ['TEAM_ACCESS_KEY_FILE']).read_text(encoding='utf-8').strip()
        request = urllib.request.Request('http://127.0.0.1:8000/ready', headers=headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            return 0 if response.status == 200 else 1
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
