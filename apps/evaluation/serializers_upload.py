"""
Separated from serializers.py because this one validates raw multipart input
(FILES + a student id), not a model — keeping it apart from the read-side
serializers makes each file's job obvious at a glance.
"""

from django.conf import settings
from rest_framework import serializers


class SheetUploadSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    pages = serializers.ListField(child=serializers.FileField(), allow_empty=False, min_length=1)

    def validate_pages(self, files):
        for f in files:
            if f.content_type not in settings.ALLOWED_UPLOAD_CONTENT_TYPES:
                raise serializers.ValidationError(f"{f.name}: only JPG, PNG and PDF are accepted.")
            if f.size > settings.MAX_UPLOAD_SIZE_BYTES:
                raise serializers.ValidationError(f"{f.name}: larger than 10 MB.")
        return files
