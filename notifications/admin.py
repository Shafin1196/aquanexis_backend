from django.contrib import admin
from .models import FirebaseDevice


@admin.register(FirebaseDevice)
class FirebaseDeviceAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'platform',
        'is_active',
        'created_at',
        'updated_at',
    )

    list_filter = (
        'platform',
        'is_active',
    )

    search_fields = (
        'user__username',
        'user__email',
        'fcm_token',
    )