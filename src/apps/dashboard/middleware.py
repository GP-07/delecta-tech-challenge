"""Content-Security-Policy for the dashboard pages and API: scripts, styles and data only from this site, no
inline scripts, no framing. The admin keeps Django's own headers (it relies on inline styles)."""

from django.conf import settings


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.setdefault("Content-Security-Policy", settings.DASHBOARD_CONTENT_SECURITY_POLICY)
            response.setdefault("Referrer-Policy", "same-origin")
        return response
