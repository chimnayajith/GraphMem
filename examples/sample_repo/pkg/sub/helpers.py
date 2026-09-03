"""Small helper module used to exercise cross-file IMPORTS resolution
and a relative import (`from .base import Base`)."""

from .base import Base


def normalize(value):
    return str(value).strip().lower()


class Formatter(Base):
    def format(self, value):
        return normalize(value)
