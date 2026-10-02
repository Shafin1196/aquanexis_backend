from django.urls import path
from .views import test_redis

urlpatterns = [
    path("test-redis/", test_redis),
]