"""Closed diagnostic vocabulary: never return arbitrary exception/UI text."""
REASONS = {
    'missing or ambiguous accessible element': 'selector_missing_or_ambiguous',
    'text interface required': 'text_interface_missing',
    'editable text unsupported': 'editable_text_unsupported',
    'editable target not visible': 'editable_not_visible',
    'Unicode readback mismatch': 'unicode_readback_mismatch',
    'action target not visible/enabled': 'action_not_available',
    'action interface required': 'action_interface_missing',
    'unique accessible action required': 'action_missing_or_ambiguous',
    'recipient changed or absent': 'recipient_changed',
    'draft protected': 'draft_protected',
    'draft changed before send': 'draft_changed',
    'ambiguous or absent exact search result': 'search_missing_or_ambiguous',
    'tree depth limit': 'tree_depth_limit',
    'unknown operation': 'unknown_operation',
    'cancelled': 'cancelled',
    'GUI disabled or calibrated profile missing': 'gui_disabled_or_profile_missing',
    'AT-SPI operation failed; no retry': 'worker_failed',
    'AT-SPI timeout; outcome may be unknown': 'worker_timeout',
    'Exact recipient identity not verified': 'recipient_changed',
    'Existing draft protected; clear manually first': 'draft_protected',
    'Exact Unicode draft verification failed': 'unicode_readback_mismatch',
    'Draft changed before send': 'draft_changed',
    'Draft changed during verification': 'draft_changed',
    'Send verification deadline exceeded': 'verification_timeout',
}
CODES = frozenset(REASONS.values()) | {'atspi_unavailable', 'profile_invalid', 'operation_failed'}


def reason_code(error):
    # Only fixed messages emitted by our code may become public diagnostics.
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return 'atspi_unavailable'
    if isinstance(error, (KeyError, FileNotFoundError)):
        return 'profile_invalid'
    message = str(error)
    return message if message in CODES else REASONS.get(message, 'operation_failed')
