"""Expected, user-facing braindump failures.

Everything under `BraindumpError` is a condition the person at the keyboard can
do something about — an id that doesn't exist, a data directory the process
isn't allowed to write to. Every surface renders these as a plain message: the
`bd` CLI prints `error:` and exits 1, the web UI answers with a status code —
so a traceback stays what it should be, the signal that braindump has a bug.
"""

from __future__ import annotations

import errno
from pathlib import Path

# EACCES/EPERM: no rights on the file or on a directory along the way — the
# usual shape inside a sandbox that only grants write access to the workspace.
# EROFS: a genuinely read-only mount.
_DENIED_ERRNOS = frozenset({errno.EACCES, errno.EPERM, errno.EROFS})

_UNWRITABLE_HINT = (
    "the braindump data directory isn't writable from here — a sandbox "
    "(codex, seatbelt, a container) or a read-only mount. Point BRAINDUMP_DIR "
    "at a writable directory, grant the sandbox write access to it, or run the "
    "command outside the sandbox."
)

_UNREADABLE_HINT = (
    "braindump can read the rest of the store but not this file — check its "
    "permissions, or what the sandbox grants read access to."
)

_NO_SPACE_HINT = "the disk holding the braindump data directory is full."


class BraindumpError(Exception):
    """Base for failures reported as a message rather than a traceback."""

    #: optional second line telling the user what to do about it
    hint: str | None = None


class EntryNotFoundError(BraindumpError):
    """No entry with this id in any index."""

    def __init__(self, entry_id: int) -> None:
        super().__init__(f"entry #{entry_id} not found")
        self.entry_id = entry_id


class StorageError(BraindumpError):
    """The braindump directory could not be read or written."""

    def __init__(
        self, message: str, *, path: Path | str | None = None, hint: str | None = None
    ) -> None:
        super().__init__(message)
        self.path = path
        self.hint = hint


class ReadOnlyStoreError(StorageError):
    """A write to the store was denied: a sandbox, a read-only mount, an owner."""


def storage_error(
    exc: OSError, path: Path | str | None = None, action: str = "access"
) -> StorageError:
    """Translate a filesystem `OSError` into a message the user can act on.

    `path` is the store path braindump was trying to touch, and passing it is
    what marks the failure as the store's. The CLI's catch-all boundary passes
    none, because there the file is usually *not* in the store (a `--body-file`
    that doesn't exist), and store-specific advice would send the user chasing
    the wrong thing.
    """
    in_store = path is not None
    target = path or exc.filename
    reason = (exc.strerror or type(exc).__name__).lower()
    message = (
        f"cannot {action} {target}: {reason}"
        if target
        else f"cannot {action}: {reason}"
    )

    if exc.errno in _DENIED_ERRNOS and in_store:
        if action == "read":
            return StorageError(message, path=target, hint=_UNREADABLE_HINT)
        return ReadOnlyStoreError(message, path=target, hint=_UNWRITABLE_HINT)
    if exc.errno == errno.ENOSPC and in_store:
        return StorageError(message, path=target, hint=_NO_SPACE_HINT)
    return StorageError(message, path=target)
