from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny


class HealthCheckViewSet(ViewSet):
    """
    Simple health check endpoint demonstrating use of drf
    """

    permission_classes = [AllowAny]

    def list(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("health-check", HealthCheckViewSet, basename="health")

app_name = "api"
urlpatterns = router.urls
