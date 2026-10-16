from django.contrib import admin

from .models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'owner', 'is_online', 'last_seen')
    search_fields = ('device_id', 'owner__username')

    def get_queryset(self, request):
        Device.mark_stale_devices_offline()
        return super().get_queryset(request)


