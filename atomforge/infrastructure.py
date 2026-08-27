"""Dependency-free errors and logging helpers for AtomForge."""

import logging


class AtomForgeError(Exception):
    pass


class UnknownAtomError(AtomForgeError, KeyError):
    pass


class UnknownPredicateError(AtomForgeError, KeyError):
    pass


class InvalidAtomOperationError(AtomForgeError):
    pass


class AlreadyDeletedError(InvalidAtomOperationError):
    pass


class InvalidConfidenceError(InvalidAtomOperationError, ValueError):
    pass


class DuplicateCurrentError(InvalidAtomOperationError):
    pass


class SchemaVersionError(AtomForgeError):
    pass


class GraphInvariantError(AtomForgeError):
    pass


class MalformedPersistenceError(AtomForgeError):
    pass


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def make_handler(
    *, level: int = logging.INFO, filename: str | None = None
) -> logging.Handler:
    handler = logging.FileHandler(filename) if filename else logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    return handler
