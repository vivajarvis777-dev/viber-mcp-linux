"""Fail closed on ambiguous desktop notification summaries (synthetic, no Viber UI)."""
from types import SimpleNamespace

from linux_domain import Ledger
from viber_auto_responder import ViberAutoResponder


def responder(tmp_path, contacts):
    return ViberAutoResponder(
        automation=SimpleNamespace(contacts=contacts),
        ledger=Ledger(tmp_path / "state"),
    )


def test_ambiguous_name_is_not_an_authorized_recipient(tmp_path):
    auto = responder(tmp_path, {
        "+380000000001": {"name": "Марія О.", "aliases": []},
        "+380000000002": {"name": "Марія П.", "aliases": []},
    })
    assert auto.resolve_recipient("Марія") is None


def test_unique_exact_contact_and_literal_number(tmp_path):
    auto = responder(tmp_path, {
        "+380000000001": {"name": "Марія О.", "aliases": ["Маша"]},
    })
    assert auto.resolve_recipient("Марія О.") == "+380000000001"
    assert auto.resolve_recipient("Маша") == "+380000000001"
    assert auto.resolve_recipient("+380000000009") == "+380000000009"


def test_unrelated_text_containing_digits_is_not_a_phone(tmp_path):
    auto = responder(tmp_path, {})
    assert auto.resolve_recipient("Group order 0000000009") is None
