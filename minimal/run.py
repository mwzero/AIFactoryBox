"""Launch the standard LiteLLM proxy; this is not another HTTP server."""
import argparse
import os
from pathlib import Path
import secrets
import sys

DIRECTORY = Path(__file__).resolve().parent


def initialize(path):
    """Create private configuration once; never overwrite an existing key."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"Configuration already exists: {path}; left unchanged.")
        return
    with os.fdopen(descriptor, "w") as file:
        file.write(
            f"LITELLM_MASTER_KEY=sk-{secrets.token_urlsafe(32)}\n"
            "OLLAMA_API_BASE=http://127.0.0.1:11434\n"
        )
    print(f"Created {path} with a random key. Keep this file private.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true", help="Create minimal/.env without overwriting it")
    parser.add_argument("--host", default="127.0.0.1", help="Listen address; default is loopback")
    parser.add_argument("--port", type=int, default=4000)
    args = parser.parse_args()
    if args.init:
        initialize(DIRECTORY / ".env")
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        parser.error("Install minimal/requirements.txt in this Python environment first.")
    load_dotenv(DIRECTORY / ".env", override=False)
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not key.startswith("sk-") or len(key) < 24 or "replace" in key.lower():
        parser.error("Set a random LITELLM_MASTER_KEY or run with --init. Refusing unauthenticated startup.")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    os.environ.setdefault("OLLAMA_API_BASE", "http://127.0.0.1:11434")
    # Preserve external proxy settings while keeping loopback traffic local.
    exclusions = os.environ.get("no_proxy") or os.environ.get("NO_PROXY", "")
    exclusions = ",".join(filter(None, [exclusions, "localhost", "127.0.0.1", "::1"]))
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = exclusions
    # A full-stack DATABASE_URL inherited from the shell must not activate a DB.
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("DIRECT_URL", None)
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    executable = Path(sys.executable).parent / ("litellm.exe" if os.name == "nt" else "litellm")
    if not executable.is_file():
        parser.error("LiteLLM executable not found next to Python; install minimal/requirements.txt.")
    os.chdir(DIRECTORY)
    os.execv(str(executable), [str(executable), "--config", str(DIRECTORY / "config.yaml"),
                            "--host", args.host, "--port", str(args.port)])


if __name__ == "__main__":
    main()
