from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from .serializers import UserRegistrationSerializer
from .models import Device, SensorLog
import os
import redis
from django.http import JsonResponse
class RegisterView(APIView):
    permission_classes = [] 

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, _ = Token.objects.get_or_create(user=user)
            device = user.device
            return Response({
                "message": "User and Device registered successfully!",
                "token": token.key,
                "device": {
                    "device_id": device.device_id,
                    "is_online": device.is_online,
                    "last_seen": device.last_seen,
                }
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = []  # Public endpoint

    def post(self, request):
        # Support login via either username or email
        identifier = request.data.get('username') or request.data.get('email')
        password = request.data.get('password')

        if not identifier or not password:
            return Response(
                {"error": "Please provide both email/username and password."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # If user entered an email, resolve it to their username
        username = identifier
        if '@' in identifier:
            try:
                user_obj = User.objects.get(email=identifier)
                username = user_obj.username
            except User.DoesNotExist:
                return Response(
                    {"error": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        user = authenticate(username=username, password=password)

        if not user:
            return Response(
                {"error": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Retrieve or generate the auth token
        token, _ = Token.objects.get_or_create(user=user)

        # Retrieve the user's paired ESP32 device
        device_info = None
        websocket_url = None
        try:
            device = user.device
            device_info = {
                "device_id": device.device_id,
                "is_online": device.is_online,
                "last_seen": device.last_seen,
                "secure_key": device.secret_key
            }
            websocket_scheme = "wss" if request.is_secure() else "ws"
            websocket_url = (
                f"{websocket_scheme}://{request.get_host()}"
                f"/ws/device/{device.device_id}/"
                f"?role=producer&key={device.secret_key}"
            )
        except Device.DoesNotExist:
            device_info = None

        return Response({
            "message": "Login successful",
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            },
            "device": device_info,
            "device_websocket_url": websocket_url
        }, status=status.HTTP_200_OK)


class SensorHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get the device belonging to the logged-in user
        try:
            device = request.user.device
        except Device.DoesNotExist:
            return Response({"error": "No device paired with this user."}, status=status.HTTP_404_NOT_FOUND)

        # Fetch the last 100 sensor logs, ordered by newest first
        logs = SensorLog.objects.filter(device=device).order_by('-timestamp')[:100]
        
        data = [{
            "pH": log.ph,
            "turbidity": log.turbidity,
            "temperature": log.temperature,
            "weight": log.weight,
            "timestamp": log.timestamp
        } for log in logs]

        return Response(data, status=status.HTTP_200_OK)

from django.http import JsonResponse
from channels.layers import get_channel_layer
import uuid


async def test_redis(request):
    try:
        channel_layer = get_channel_layer()

        channel_name = "test_" + uuid.uuid4().hex

        await channel_layer.group_add(
            "aquanexis_test_group",
            channel_name,
        )

        await channel_layer.group_discard(
            "aquanexis_test_group",
            channel_name,
        )

        return JsonResponse({
            "channels": "working",
        })

    except Exception as e:
        return JsonResponse({
            "channels": "error",
            "error": str(e),
        }, status=500)