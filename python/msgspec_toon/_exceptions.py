"""Package-owned public exception contracts."""

from __future__ import annotations


class TypePlanError(TypeError):
    """An annotation cannot be compiled into a supported typed codec plan."""

    __slots__ = ("code", "path")

    def __init__(self, *, code: str, path: tuple[str, ...]) -> None:
        self.code = code
        self.path = path
        location = "$" + "".join(
            component if component.startswith("[") else f".{component}" for component in path
        )
        super().__init__(f"unsupported type annotation at {location} ({code})")
