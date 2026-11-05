from django.urls import path
from streaming.views import RegisterView, LoginView, SensorHistoryView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('sensors/history/', SensorHistoryView.as_view(), name='sensor-history'),
]