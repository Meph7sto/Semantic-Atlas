"""Tests for suppressing noisy internal endpoint access logs."""

import logging

from backend_business.main import (
    InternalEndpointsFilter,
    configure_uvicorn_access_log_filter,
)


def _build_record(level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_internal_endpoints_filter_drops_info_logs():
    record = _build_record(
        logging.INFO,
        'None:0 - "GET /api/v2/_internals/actors/stats HTTP/1.0" 200 OK',
    )

    assert InternalEndpointsFilter().filter(record) is False


def test_internal_endpoints_filter_keeps_non_internal_or_non_info():
    public_info = _build_record(
        logging.INFO,
        'None:0 - "GET /api/v2/requirement-actor/stats HTTP/1.0" 200 OK',
    )
    internal_warning = _build_record(
        logging.WARNING,
        'None:0 - "GET /api/v2/_internals/actors/stats HTTP/1.0" 500 Internal Server Error',
    )

    log_filter = InternalEndpointsFilter()
    assert log_filter.filter(public_info) is True
    assert log_filter.filter(internal_warning) is True


def test_configure_uvicorn_access_log_filter_is_idempotent():
    logger = logging.getLogger("uvicorn.access")
    original_filters = list(logger.filters)

    try:
        logger.filters = [
            filt for filt in logger.filters if not isinstance(filt, InternalEndpointsFilter)
        ]

        configure_uvicorn_access_log_filter()
        configure_uvicorn_access_log_filter()

        matched = [
            filt for filt in logger.filters if isinstance(filt, InternalEndpointsFilter)
        ]
        assert len(matched) == 1
    finally:
        logger.filters = original_filters
