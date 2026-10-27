"""Login of the dashboard, with a limit on failed attempts: after LOGIN_MAX_FAILURES wrong passwords for a user
name (from any address) or from an address (for any user name), logging in is refused for LOGIN_LOCKOUT_SECONDS.
"""

from django import forms
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache

from apps.dashboard.constants import LOCKED_MESSAGE


def _keys(request, username: str) -> list[str]:
    return [f"login-failures:user:{username.lower()}", f"login-failures:ip:{request.META.get('REMOTE_ADDR', '')}"]


class ThrottledAuthenticationForm(AuthenticationForm):
    def clean(self):
        keys = _keys(self.request, self.data.get("username", "")[:150])
        if any((cache.get(key) or 0) >= settings.LOGIN_MAX_FAILURES for key in keys):
            raise forms.ValidationError(LOCKED_MESSAGE, code="locked")
        try:
            return super().clean()
        except forms.ValidationError:
            for key in keys:
                cache.add(key, 0, settings.LOGIN_LOCKOUT_SECONDS)
                cache.incr(key)
            raise


class LoginView(auth_views.LoginView):
    form_class = ThrottledAuthenticationForm
    redirect_authenticated_user = True
