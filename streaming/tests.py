from asgiref.sync import async_to_sync
from datetime import timedelta
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


from .consumers import VideoStreamConsumer
from .models import Device, SensorLog




class SensorHistoryViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sensor-owner", password="test-pass")
        self.device = Device.objects.create(device_id="device-1", owner=self.user)
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.url = "/api/sensors/history/"


    def test_field_filter_returns_only_non_null_values_for_requested_sensor(self):
        SensorLog.objects.create(device=self.device, temperature=22.5, ph=7.1)
        SensorLog.objects.create(device=self.device, temperature=None, ph=7.3)


        response = self.client.get(self.url, {"field": "temperature"})


        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["temperature"], 22.5)
        self.assertEqual(set(response.data[0]), {"temperature", "timestamp"})


    def test_field_filter_returns_all_matching_readings_not_only_100(self):
        SensorLog.objects.bulk_create(
            [
                SensorLog(device=self.device, temperature=float(index))
                for index in range(105)
            ]
        )


        response = self.client.get(self.url, {"field": "temperature"})


        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 105)


    def test_invalid_field_returns_bad_request(self):
        for field in ("salinity", ""):
            with self.subTest(field=field):
                response = self.client.get(self.url, {"field": field})


                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.data)


    def test_without_field_keeps_full_sensor_history(self):
        SensorLog.objects.create(device=self.device, temperature=22.5, ph=7.1)


        response = self.client.get(self.url)


        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            set(response.data[0]),
            {"pH", "turbidity", "temperature", "weight", "timestamp"},
        )


    def test_websocket_saves_turbidity_voltage(self):
        consumer = VideoStreamConsumer()
        async_to_sync(consumer.save_sensor_log)(
            self.device.device_id,
            {
                "temperature": 26.81,
                "turbidity_raw": 3218,
                "turbidity_voltage": 4.623,
                "weight_grams": 93.76,
            },
        )


        log = SensorLog.objects.get(device=self.device)
        self.assertEqual(log.turbidity, 4.623)
        self.assertEqual(log.weight, 93.76)

    def test_websocket_skips_empty_sensor_log(self):
        consumer = VideoStreamConsumer()

        async_to_sync(consumer.save_sensor_log)(
            self.device.device_id,
            {
                "pH": None,
                "temperature": None,
                "turbidity_voltage": None,
                "weight_grams": None,
            },
        )

        self.assertFalse(SensorLog.objects.filter(device=self.device).exists())

    def test_stale_producer_is_marked_offline_after_timeout(self):
        consumer = VideoStreamConsumer()
        consumer.connection_id = "6a1e0e1f-5dd2-4c3b-94e4-2f7f2c5f7d6d"
        self.device.is_online = True
        self.device.producer_connection_id = consumer.connection_id
        self.device.save(
            update_fields=["is_online", "producer_connection_id"]
        )
        Device.objects.filter(pk=self.device.pk).update(
            last_seen=timezone.now() - timedelta(seconds=11)
        )

        changed = async_to_sync(consumer.set_stale_producer_offline)(
            self.device.device_id
        )

        self.assertTrue(changed)
        self.device.refresh_from_db()
        self.assertFalse(self.device.is_online)
        self.assertIsNone(self.device.producer_connection_id)

    def test_stale_connection_cannot_mark_new_producer_offline(self):
        old_consumer = VideoStreamConsumer()
        old_consumer.connection_id = "6a1e0e1f-5dd2-4c3b-94e4-2f7f2c5f7d6d"
        new_consumer = VideoStreamConsumer()
        new_consumer.connection_id = "a8e6dd4b-f89a-4ce2-bc5b-4e1e438c5ce4"
        self.device.is_online = True
        self.device.producer_connection_id = new_consumer.connection_id
        self.device.save(
            update_fields=["is_online", "producer_connection_id"]
        )

        changed = async_to_sync(old_consumer.set_stale_producer_offline)(
            self.device.device_id
        )

        self.assertFalse(changed)
        self.device.refresh_from_db()
        self.assertTrue(self.device.is_online)
        self.assertEqual(
            str(self.device.producer_connection_id),
            new_consumer.connection_id,
        )

    def test_mark_stale_devices_offline_persists_status_cleanup(self):
        self.device.is_online = True
        self.device.producer_connection_id = "6a1e0e1f-5dd2-4c3b-94e4-2f7f2c5f7d6d"
        self.device.save(update_fields=["is_online", "producer_connection_id"])
        Device.objects.filter(pk=self.device.pk).update(
            last_seen=timezone.now() - timedelta(seconds=11)
        )

        updated = Device.mark_stale_devices_offline()

        self.assertEqual(updated, 1)
        self.device.refresh_from_db()
        self.assertFalse(self.device.is_online)
        self.assertIsNone(self.device.producer_connection_id)
