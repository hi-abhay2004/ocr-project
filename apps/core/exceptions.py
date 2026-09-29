import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def field_keyed_exception_handler(exc, context):
    """
    DRF's default handler already returns the two shapes the frontend expects
    (`errorMessage()` in frontend/src/lib/axios.ts):

      - {"detail": "..."}           for auth / permission / not-found / throttling
      - {"field_name": ["msg"]}     for serializer ValidationError

    This wrapper only adds one thing DRF doesn't: an unhandled non-DRF exception
    (a bug) must still come back as JSON, not an HTML debug/500 page. A crop that
    fails to decode or a task that raises should surface as a mark of FAILED on
    the sheet with a message — not a broken response the frontend can't parse.
    """
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    logger.exception("Unhandled exception in %s", context.get("view"))
    return Response({"detail": "An unexpected error occurred."}, status=500)
