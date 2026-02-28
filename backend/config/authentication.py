from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    SessionAuthentication that bypasses CSRF checks.
    Used for SPA API endpoints protected by CORS instead.
    """
    def enforce_csrf(self, request):
        return
