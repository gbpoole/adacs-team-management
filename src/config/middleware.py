from django.http import HttpResponse


class HealthCheckMiddleware:
    """Return 200 for /health/ before SecurityMiddleware validates the Host header.

    Docker healthcheck probes send Host: localhost which Django's ALLOWED_HOSTS
    would otherwise reject in production.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
