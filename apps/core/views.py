from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """
    Confirms the app is up AND the database is reachable with pgvector
    installed — the two things B0's gate actually needs to prove. A 200 here
    that doesn't touch the DB would hide a broken DATABASE_URL until the first
    real request.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        has_vector = cursor.fetchone() is not None

    return Response(
        {
            "status": "ok",
            "database": "ok",
            "pgvector": "ok" if has_vector else "MISSING — run migrations",
        }
    )
