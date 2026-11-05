from rest_framework import serializers


class FirebaseDeviceSerializer(serializers.Serializer):

    fcm_token = serializers.CharField(
        max_length=500
    )

    platform = serializers.ChoiceField(
        choices=['android', 'ios']
    )