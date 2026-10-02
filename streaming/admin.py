from django.contrib import admin

from .models import Device

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'owner', 'is_online', 'last_seen')
    search_fields = ('device_id', 'owner__username')
