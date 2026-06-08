"""Run the sandbox-runner service with `python -m kortny.sandbox_runner`."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "kortny.sandbox_runner.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8090,
    )


if __name__ == "__main__":
    main()
