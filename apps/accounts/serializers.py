import re

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.students.models import Student

from .models import User

USN_RE = re.compile(r"^[0-9A-Z]{6,15}$")


class RegisterSerializer(serializers.Serializer):
    """
    POST /api/auth/register/ — BACKEND_PLAN.md §B1, contract fixed by
    FRONTEND_PLAN.md §3.4 / frontend/src/types/api.ts RegisterInput.

    `usn` is required for STUDENT and rejected for TEACHER; both checks live
    in `validate()` because they depend on `role`, not on `usn` alone.
    """

    username = serializers.CharField(max_length=150)
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=User.Role.choices)
    usn = serializers.CharField(max_length=15, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        role = attrs.get("role")
        usn = (attrs.get("usn") or "").strip().upper()

        if role == User.Role.STUDENT:
            if not usn:
                raise serializers.ValidationError({"usn": "This field is required for students."})
            if not USN_RE.fullmatch(usn):
                raise serializers.ValidationError({"usn": "USN looks malformed."})
            # A Student row can already exist un-claimed (a teacher imported the
            # class list by CSV before this person ever signed up) — that case
            # is a LINK, not a conflict. Only a row that already has a `user`
            # attached is a genuine duplicate registration.
            existing = Student.objects.filter(usn=usn).first()
            if existing is not None and existing.user_id is not None:
                raise serializers.ValidationError(
                    {"usn": "A student with this USN is already registered."}
                )
        elif usn:
            raise serializers.ValidationError({"usn": "USN must not be set for teacher accounts."})

        attrs["usn"] = usn
        return attrs

    def create(self, validated_data):
        usn = validated_data.pop("usn", "")
        password = validated_data.pop("password")
        role = validated_data["role"]

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            full_name=validated_data["full_name"],
            role=role,
            password=password,
        )

        if role == User.Role.STUDENT:
            student, _created = Student.objects.get_or_create(
                usn=usn,
                defaults={"name": validated_data["full_name"], "email": validated_data["email"]},
            )
            student.user = user
            if not student.email:
                student.email = validated_data["email"]
            student.save(update_fields=["user", "email"])

        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "full_name", "role"]
