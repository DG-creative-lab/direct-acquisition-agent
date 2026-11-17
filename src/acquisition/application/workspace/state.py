"""Explicit state collaborators assembled by the composition root."""
from collections.abc import Callable
from dataclasses import dataclass
from acquisition.conversations import WorkspaceState
from .ports import WorkspaceControlStore, WorkspaceStorageFaults


@dataclass(frozen=True)
class WorkspaceStateAccess:
    control: WorkspaceControlStore
    authority: Callable[[], WorkspaceState]
    storage_faults: WorkspaceStorageFaults
