"""Workspace startup, exclusive root ownership and scheduler lifetime."""
import argparse
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from acquisition.bootstrap import build_workspace, build_workspace_http
from acquisition.contracts import Conflict
from acquisition.local_root import require_live_root, workspace_root_lock


class WorkspaceServer:
    """Own the root lock until transport handlers and the scheduler have stopped."""

    def __init__(self, port, workspace, assets):
        self.workspace = workspace
        self.preparation_stop = threading.Event()
        self.preparation_worker = None
        require_live_root(workspace.root)
        self.root_lock = ExitStack()
        self.root_lock.enter_context(workspace_root_lock(workspace.root))
        self._http = None
        try:
            self._http = build_workspace_http(port, workspace, assets)
            workspace.recover_execution()
            workspace.preparations.recover("local-conversations")
            workspace.recover_copy_revisions()
            workspace.recover_actions()
        except BaseException:
            if self._http is not None:
                self._http.server_close()
            self.root_lock.close()
            raise
        self.preparation_worker = threading.Thread(target=self._continue_preparations, daemon=True)
        self.preparation_worker.start()

    @property
    def server_port(self):
        return self._http.server_port

    @property
    def token(self):
        return self._http.token

    @property
    def assets(self):
        return self._http.assets

    def serve_forever(self, poll_interval=0.5):
        self._http.serve_forever(poll_interval=poll_interval)

    def shutdown(self):
        self._http.shutdown()

    def server_close(self):
        with self._http.request_gate:
            self._http.closing = True
            self.preparation_stop.set()
        self._http.server_close()
        if self.preparation_worker is not None:
            self.preparation_worker.join()
        self.root_lock.close()

    def _continue_preparations(self):
        next_report_check = time.monotonic()
        while not self.preparation_stop.wait(0.25):
            if time.monotonic() >= next_report_check:
                try:
                    self.workspace.advance_report_monitoring()
                except Exception:
                    pass  # The next pass rechecks the same scoped schedules.
                next_report_check = time.monotonic() + 2
            try:
                self.workspace.models.expire()
                self.workspace.advance_preparations()
            except Exception:
                # A storage interruption leaves original durable identities intact.
                # No alternate run/key is ever created by this scheduler.
                continue



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
    assets = Path(__file__).resolve().parents[3] / "frontend/dist"
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
