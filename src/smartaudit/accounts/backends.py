from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Authenticate e-mail case-insensitively without leaking user existence."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        raw_email = username or kwargs.get("email") or ""
        email = user_model.objects.canonicalize_email(raw_email)

        try:
            user = user_model.objects.get(email__iexact=email)
        except user_model.DoesNotExist:
            user_model().set_password(password)
            return None
        except user_model.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
