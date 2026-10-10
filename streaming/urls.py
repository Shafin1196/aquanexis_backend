from django.urls import path
from .views import database_status, test_redis

urlpatterns = [
    path("test-redis/", test_redis),
    path("database-status/", database_status),
]