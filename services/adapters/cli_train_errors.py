# SPDX-License-Identifier: MIT
"""Exceptions for CLI training via db_bridge remote shell."""

from __future__ import annotations

from typing import Any


class CLITrainError(RuntimeError):
    """Base error for CLI train transport and adapter."""

    def __init__(self, message: str, *, body: Any = None):
        super().__init__(message)
        self.body = body


class TransportError(CLITrainError):
    """Supabase insert or poll HTTP failure."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: Any = None,
    ):
        super().__init__(message, body=body)
        self.status = status


class TrainerCLIError(CLITrainError):
    """Remote command finished with a non-success terminal status."""

    def __init__(
        self,
        message: str,
        *,
        terminal_status: str | None = None,
        exit_code: int | None = None,
        body: Any = None,
    ):
        super().__init__(message, body=body)
        self.terminal_status = terminal_status
        self.exit_code = exit_code


class TrainerTimeoutError(CLITrainError):
    """Remote command timed out or poll budget was exceeded."""

    def __init__(
        self,
        message: str,
        *,
        cmd_id: str | None = None,
        body: Any = None,
    ):
        super().__init__(message, body=body)
        self.cmd_id = cmd_id
