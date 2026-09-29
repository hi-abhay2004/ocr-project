from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import RegisterSerializer, UserSerializer


class LoginView(TokenObtainPairView):
    """SimpleJWT's default response is already {access, refresh} — exactly
    frontend/src/types/api.ts TokenPair, so no serializer override needed."""

    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_scope = "auth"


class RegisterView(APIView):
    """
    Returns a token pair, not just the created user — a successful signup logs
    the person straight in rather than bouncing them to a login form they've
    effectively already filled (frontend/src/pages/Signup.tsx).
    """

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
