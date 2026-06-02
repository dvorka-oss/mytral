# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import abc
import logging
import os
import sys

import structlog

# flags
ON_PYTHONANYWHERE = bool(os.getenv("PYTHONANYWHERE_DOMAIN"))

#
# MyTraL logging infrastructure
#


def configure_structlog(debug: bool) -> None:
    """Configure structlog globally for the entire MyTraL application.

    Must be called once at startup, before any logger is obtained or used.
    Two rendering modes are supported:

    - **debug=True** — human-readable colored console output via
      ``ConsoleRenderer``.  Suitable for local development.
    - **debug=False** — machine-readable JSON output via ``JSONRenderer``.
      One JSON object per line; ready for log aggregators (Datadog, Loki or Splunk)

    Parameters
    ----------
    debug : bool
        When ``True`` use the pretty dev renderer, otherwise emit JSON.
    """
    log_output = sys.stderr if ON_PYTHONANYWHERE else sys.stdout
    log_level = logging.DEBUG if debug else logging.INFO

    # processors applied to every log event regardless of renderer
    shared_processors: list = [
        # merge per-request / per-task context vars (request_id, user, ...)
        structlog.contextvars.merge_contextvars,
        # add "level" key to the event dict
        structlog.processors.add_log_level,
        # add "timestamp" key in ISO-8601 UTC format
        structlog.processors.TimeStamper(fmt="iso"),
        # render stack_info= kwarg if provided
        structlog.processors.StackInfoRenderer(),
        # show exception stack traces
        structlog.processors.dict_tracebacks,
    ]

    if debug:
        renderer = structlog.dev.ConsoleRenderer()
        processors = shared_processors + [renderer]
    else:
        processors = shared_processors + [
            # format exc_info tuple > "exception" string before JSON encoding
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        # filter events below the configured level before they reach the chain
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=log_output),
        # cache the logger pipeline after first use for best performance
        cache_logger_on_first_use=True,
    )


class MytralLogger(abc.ABC):
    def info(self, msg, *args, **kwargs):
        raise NotImplementedError

    def debug(self, msg, *args, **kwargs):
        raise NotImplementedError

    def warning(self, msg, *args, **kwargs):
        raise NotImplementedError

    def error(self, msg, *args, **kwargs):
        raise NotImplementedError

    def exception(self, msg, exc_info, *args, **kwargs):
        self.error(msg, exc_info=exc_info, *args, **kwargs)


class MytralStructLogger(MytralLogger):
    """Structlog-backed logger implementing the ``MytralLogger`` interface.

    Wraps a ``structlog`` bound logger so that all call sites that use the
    ``logger.info/debug/warning/error(msg)`` pattern continue to work without
    any changes.  New code should prefer the structured form::

        logger.info("user logged in", user=username, ip=remote_addr)

    Parameters
    ----------
    name : str
        Logger name embedded in every event (visible in debug renderer).
    """

    def __init__(self, name: str = "mytral"):
        self._logger = structlog.get_logger(name)

    def bind(self, **kwargs) -> "MytralStructLogger":
        """Return a new logger with additional permanently-bound context fields.

        The original logger is not mutated; the returned logger carries all
        existing bindings plus the new ``kwargs``.
        """
        new: MytralStructLogger = MytralStructLogger.__new__(MytralStructLogger)
        new._logger = self._logger.bind(**kwargs)
        return new

    def info(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self._logger.info(msg, **kwargs)

    def debug(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self._logger.debug(msg, **kwargs)

    def warning(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self._logger.warning(msg, **kwargs)

    def error(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self._logger.error(msg, **kwargs)


class MytralFileLogger(MytralLogger):
    """Standard-library file logger (kept for backward compatibility)."""

    FORMATTER = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    def __init__(self, logger_name: str, log_file: str, log_level=logging.INFO):
        handler = logging.FileHandler(log_file)
        handler.setFormatter(MytralFileLogger.FORMATTER)

        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(log_level)
        self.logger.addHandler(handler)

    def info(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self.logger.info(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self.logger.debug(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        # WARN: the logger does not support positional args - use keyword args
        self.logger.error(msg, *args, **kwargs)


class MytralPrintLogger(MytralLogger):
    """Print-based logger (kept for backward compatibility)."""

    def __init__(self):
        pass

    def info(self, msg, *args, **kwargs):
        if ON_PYTHONANYWHERE:
            print(msg, file=sys.stderr)
        else:
            print(msg)

    def debug(self, msg, *args, **kwargs):
        if ON_PYTHONANYWHERE:
            print(msg, file=sys.stderr)
        else:
            print(msg)

    def warning(self, msg, *args, **kwargs):
        print(msg, file=sys.stderr)

    def error(self, msg, *args, **kwargs):
        print(msg, file=sys.stderr)
