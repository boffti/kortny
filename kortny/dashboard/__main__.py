"""Run the dashboard service."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "kortny.dashboard.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8080,
    )


if __name__ == "__main__":
    main()
