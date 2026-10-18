from types import SimpleNamespace
import pytest
from pydantic import BaseModel, Field
from mcp.types import ToolAnnotations
from compat.hermes_sdk2_readonly import _annotation_read_only_hint


class SDK2Shape(BaseModel):
    # Matches the actual installed Hermes SDK's introspected field/alias.
    read_only_hint: bool | None = Field(default=None, alias='readOnlyHint')


@pytest.mark.parametrize('annotations', [
    ToolAnnotations(readOnlyHint=True),
    SDK2Shape.model_validate({'readOnlyHint': True}),
    {'readOnlyHint': True}, {'read_only_hint': True},
    {'readOnlyHint': True, 'read_only_hint': True},
])
def test_explicit_read_only_accepted_in_both_sdk_generations(annotations):
    assert _annotation_read_only_hint(SimpleNamespace(annotations=annotations)) is True


@pytest.mark.parametrize('annotations', [
    None, {}, {'readOnlyHint': 'true'}, {'read_only_hint': 1},
    {'readOnlyHint': True, 'read_only_hint': False},
    {'readOnlyHint': False, 'read_only_hint': True},
    ToolAnnotations(readOnlyHint=False), SDK2Shape(),
    SimpleNamespace(read_only_hint=None), SimpleNamespace(),
])
def test_missing_false_malformed_and_conflicting_hints_stay_protected(annotations):
    assert _annotation_read_only_hint(SimpleNamespace(annotations=annotations)) is False
