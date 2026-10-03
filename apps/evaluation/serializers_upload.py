"""
Separated from serializers.py because this one validates raw multipart input
(FILES + a student id), not a model — keeping it apart from the read-side
serializers makes each file's job obvious at a glance.
"""

from django.conf import settings
from rest_framework import serializers

# Real file signatures, not the client-supplied multipart Content-Type
# header — that header is just a string the client chose to send and is
# trivial to spoof (e.g. a renamed executable declared as "image/jpeg").
# Checked against the file's own first bytes instead.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "application/pdf": (b"%PDF-",),
}


def _sniff_content_type(f) -> str | None:
    header = f.read(8)
    f.seek(0)
    for content_type, signatures in _SIGNATURES.items():
        if any(header.startswith(sig) for sig in signatures):
            return content_type
    return None


class SheetUploadSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    pages = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        min_length=1,
        max_length=settings.MAX_UPLOAD_PAGE_COUNT,
    )

    def validate_pages(self, files):
        total_size = 0
        for f in files:
            declared = f.content_type
            if declared not in settings.ALLOWED_UPLOAD_CONTENT_TYPES:
                raise serializers.ValidationError(f"{f.name}: only JPG, PNG and PDF are accepted.")
            if f.size > settings.MAX_UPLOAD_SIZE_BYTES:
                raise serializers.ValidationError(f"{f.name}: larger than 10 MB.")
            actual = _sniff_content_type(f)
            if actual is None or actual != declared:
                raise serializers.ValidationError(
                    f"{f.name}: file content doesn't match a JPG, PNG or PDF."
                )
            total_size += f.size
        if total_size > settings.MAX_UPLOAD_TOTAL_SIZE_BYTES:
            raise serializers.ValidationError(
                f"Upload is {total_size // (1024 * 1024)} MB total — "
                f"the limit is {settings.MAX_UPLOAD_TOTAL_SIZE_BYTES // (1024 * 1024)} MB."
            )
        return files
