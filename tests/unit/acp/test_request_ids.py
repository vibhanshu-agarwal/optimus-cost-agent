import pytest

from optimus.acp.errors import DUPLICATE_REQUEST_ID
from optimus.acp.request_ids import DuplicateRequestId, RequestIdTracker


def test_tracker_accepts_first_request_id():
    tracker = RequestIdTracker()

    tracker.remember("req-1")

    assert tracker.seen("req-1") is True


def test_tracker_rejects_duplicate_request_id_with_app_code():
    tracker = RequestIdTracker()
    tracker.remember(42)

    with pytest.raises(DuplicateRequestId) as exc_info:
        tracker.remember(42)

    assert exc_info.value.code == DUPLICATE_REQUEST_ID
    assert exc_info.value.request_id == 42
