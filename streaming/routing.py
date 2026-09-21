from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # This regex captures the device_id from the URL
    re_path(r'ws/device/(?P<device_id>\w+)/$', consumers.VideoStreamConsumer.as_asgi()),
]