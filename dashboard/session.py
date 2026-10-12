"""Helpers for Streamlit login state.

A page rerun may find a saved token without its matching user profile.
Keeping the recovery logic separate makes it easy to test without Streamlit.
"""

VALID_ROLES = {'admin', 'vendor', 'customer'}


def resolve_user(state, fetch_user):
    """Return the signed-in user, restoring it from the API if necessary.

    An invalid or expired token clears the partial session so the sign-in page
    can be shown instead of trying to access a missing state['user'].
    """
    if not state.get('token'):
        state.pop('user', None)
        return None

    user = state.get('user')
    if isinstance(user, dict) and user.get('role') in VALID_ROLES and user.get('email'):
        return user

    user = fetch_user()
    if not isinstance(user, dict) or user.get('role') not in VALID_ROLES or not user.get('email'):
        state.pop('token', None)
        state.pop('user', None)
        return None

    state['user'] = user
    return user
