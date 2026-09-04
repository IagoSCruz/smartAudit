from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from smartaudit.accounts.managers import UserManager


class User(AbstractUser):
    """Global identity; tenant access is represented by Membership."""

    username = None
    email = models.EmailField("e-mail", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_user_email_ci_unique",
            )
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.__class__.objects.canonicalize_email(self.email)
        return super().save(*args, **kwargs)
