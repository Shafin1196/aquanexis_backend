from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Device

class UserRegistrationSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'device_id']

    def validate_device_id(self, value):
        # 1. Does this device exist in your system at all?
        # (Optional: Remove this check if you want devices created dynamically)
        try:
            device = Device.objects.get(device_id=value)
        except Device.DoesNotExist:
            raise serializers.ValidationError("Invalid Device ID. This hardware does not exist.")

        # 2. IS IT ALREADY REGISTERED? (Your exact rule)
        if device.owner is not None:
            raise serializers.ValidationError("This Device ID is already registered to another user.")
            
        return value

    def create(self, validated_data):
        device_id = validated_data.pop('device_id')
        password = validated_data.pop('password')
        
        # Create the new user
        user = User.objects.create_user(**validated_data, password=password)
        
        # Assign the device to this new user
        device = Device.objects.get(device_id=device_id)
        device.owner = user
        device.save()
        
        return user