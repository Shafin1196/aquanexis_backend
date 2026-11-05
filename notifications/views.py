from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import FirebaseDevice
from .serializers import FirebaseDeviceSerializer


class RegisterFirebaseDeviceView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = FirebaseDeviceSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        fcm_token = serializer.validated_data['fcm_token']
        platform = serializer.validated_data['platform']

        FirebaseDevice.objects.update_or_create(
            fcm_token=fcm_token,
            defaults={
                'user': request.user,
                'platform': platform,
                'is_active': True,
            }
        )

        return Response(
            {
                'message': 'FCM device registered successfully.'
            },
            status=status.HTTP_200_OK
        )