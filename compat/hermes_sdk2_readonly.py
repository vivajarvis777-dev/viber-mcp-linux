"""Proposed Hermes SDK v1/v2 compatibility fix; not installed or imported by MCP."""


def _annotation_read_only_hint(mcp_tool: object) -> bool:
    """Require an explicit boolean True; conflicting aliases remain write-capable."""
    annotations = getattr(mcp_tool, 'annotations', None)
    values = []
    for key in ('readOnlyHint', 'read_only_hint'):
        if isinstance(annotations, dict):
            if key in annotations:
                values.append(annotations[key])
        else:
            missing = object()
            value = getattr(annotations, key, missing)
            if value is not missing:
                values.append(value)
    return bool(values) and all(value is True for value in values)
