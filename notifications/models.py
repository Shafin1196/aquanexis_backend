from django.db import models
from django.conf import settings


class FirebaseDevice(models.Model):

    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='firebase_devices'
    )

    fcm_token = models.CharField(
        max_length=500,
        unique=True
    )

    platform = models.CharField(
        max_length=20,
        choices=PLATFORM_CHOICES
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.platform}"