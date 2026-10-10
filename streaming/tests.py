from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
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
            },
        )


        log = SensorLog.objects.get(device=self.device)
        self.assertEqual(log.turbidity, 4.623)





