from django.contrib import admin
from django.urls import path
from streaming.views import RegisterView, LoginView, SensorHistoryView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/register/', RegisterView.as_view(), name='register'),
    path('api/login/', LoginView.as_view(), name='login'),
    path('api/sensors/history/', SensorHistoryView.as_view(), name='sensor-history'),
]