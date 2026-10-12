"""Regression tests for Streamlit login reruns and partial session state."""
import sys
from pathlib import Path

# Streamlit executes dashboard.py with its own folder on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from session import resolve_user


def test_missing_token_clears_stale_user():
    state = {'user': {'role': 'admin', 'email': 'admin@example.com'}}
    assert resolve_user(state, lambda: (_ for _ in ()).throw(AssertionError('Unexpected API call'))) is None
    assert 'user' not in state


def test_token_without_user_restores_profile():
    state = {'token': 'valid-token'}
    expected = {'email': 'vendor@example.com', 'role': 'vendor'}
    assert resolve_user(state, lambda: expected) == expected
    assert state['user'] == expected


def test_invalid_token_clears_partial_session():
    state = {'token': 'expired-token'}
    assert resolve_user(state, lambda: None) is None
    assert state == {}


def test_existing_user_does_not_make_extra_api_call():
    expected = {'email': 'customer@example.com', 'role': 'customer'}
    state = {'token': 'valid-token', 'user': expected}
    assert resolve_user(state, lambda: (_ for _ in ()).throw(AssertionError('Unexpected API call'))) == expected


def test_malformed_profile_is_rejected():
    state = {'token': 'valid-token', 'user': {'email': 'hmm@example.com'}}
    assert resolve_user(state, lambda: {'email': 'x@example.com', 'role': 'wrong'}) is None
    assert state == {}
