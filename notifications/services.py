from firebase_admin import messaging
from .firebase import initialize_firebase
from .models import FirebaseDevice


def send_detection_alert(user, device_id, confidence):
    initialize_firebase()

    devices = FirebaseDevice.objects.filter(
        user=user,
        is_active=True,
    )

    if not devices.exists():
        return {
            "success": False,
            "message": "No active FCM devices found.",
        }

    results = []

    for device in devices:
        message = messaging.Message(
            notification=messaging.Notification(
                title="Abnormal Activity Alert",
                body=(
                    f"Abnormal activity detected on device {device_id} "
                    f"with {confidence:.0%} confidence."
                ),
            ),
            data={
                "type": "detection_alert",
                "device_id": str(device_id),
                "confidence": str(confidence),
            },
            token=device.fcm_token,
        )

        try:
            response = messaging.send(message)
            results.append({
                "token": device.fcm_token[:15] + "...",
                "success": True,
                "message_id": response,
            })
        except Exception as error:
            results.append({
                "token": device.fcm_token[:15] + "...",
                "success": False,
                "error": str(error),
            })

    return results


def send_test_notification(user):
    initialize_firebase()

    devices = FirebaseDevice.objects.filter(
        user=user,
        is_active=True
    )

    if not devices.exists():
        return {
            "success": False,
            "message": "No active FCM devices found."
        }

    results = []

    for device in devices:
        message = messaging.Message(
            notification=messaging.Notification(
                title="AquaNexis ",
                body="Abnormal activity detected!"
            ),
            data={
                "type": "test",
                "message": "FCM test notification"
            },
            token=device.fcm_token,
        )

        try:
            response = messaging.send(message)

            results.append({
                "token": device.fcm_token[:15] + "...",
                "success": True,
                "message_id": response,
            })

        except Exception as error:
            results.append({
                "token": device.fcm_token[:15] + "...",
                "success": False,
                "error": str(error),
            })

    return results