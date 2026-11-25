"""Real browser server with a test-only clock inside the authored source window.

Use the normal startup and recovery path. No production clock override is
exposed, and model credentials remain the offline sentinel set by Playwright.
"""
from functools import partial
from unittest.mock import patch

from acquisition.entrypoints import workspace


if __name__ == "__main__":
    with patch.object(workspace, "build_workspace",
                      partial(workspace.build_workspace, real_clock=lambda: 1793404800.)):
        workspace.main()
