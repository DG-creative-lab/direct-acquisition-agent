"""Loopback workspace startup and compatibility transport exports."""
import argparse
from pathlib import Path
from acquisition.bootstrap import build_workspace
from acquisition.contracts import Conflict
from acquisition.local_root import require_live_root
from acquisition.transport.workspace_http import WorkspaceServer, Handler


def main():
    parser = argparse.ArgumentParser(description="Local synthetic React workspace. No hosted authentication or delivery.")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--root", type=Path, default=Path(".local/workspace"))
    parser.add_argument('--verified-admissions',action='store_true',help='Select verified admissions after the server lock is acquired. Execution stays paused.')
    args = parser.parse_args()
    try:
        require_live_root(args.root)
    except Conflict as error:
        parser.exit(2, str(error) + "\n")
    assets = Path(__file__).resolve().parents[2] / "frontend/dist"
    if not (assets / "index.html").exists():
        parser.error(
            "Build the interface first: pnpm --dir frontend install --frozen-lockfile "
            "&& pnpm --dir frontend run build"
        )
    try:
        server = WorkspaceServer(args.port, build_workspace(args.root,verified_admissions=args.verified_admissions), assets)
    except (Conflict, BlockingIOError) as error:
        parser.exit(2, str(error) + "\n")
    print(f"Synthetic workspace: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
