"""Shared lightweight types for Meridian Alpha."""

type JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
