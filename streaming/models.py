from django.db import models
from django.contrib.auth.models import User
import uuid

class Device(models.Model):
    # The unique hardware ID (e.g., printed on the bottom of the ESP32)
    device_id = models.CharField(max_length=100, unique=True)
    
    # A password specifically for the ESP32 to connect to WebSockets
    secret_key = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # Online status tracking
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)
    
    # The owner. OneToOneField means a device can only have ONE owner.
    # null=True allows you to add devices to the DB before a user buys/claims them.
    owner = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.device_id


class SensorLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='sensor_logs')
    ph = models.FloatField(null=True, blank=True)
    turbidity = models.FloatField(null=True, blank=True)
    temperature = models.FloatField(null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)  # <-- Added weight sensor field
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device.device_id} - {self.timestamp}"