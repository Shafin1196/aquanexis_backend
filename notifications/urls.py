from django.urls import path

from .views import RegisterFirebaseDeviceView


urlpatterns = [
    path(
        'devices/register/',
        RegisterFirebaseDeviceView.as_view(),
        name='register-firebase-device'
    ),
]