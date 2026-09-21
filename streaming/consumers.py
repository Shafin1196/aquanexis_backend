import cv2
import numpy as np
import asyncio
import json
import time
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework.authtoken.models import Token
from ultralytics import YOLO
from .models import Device, SensorLog
# best.pt
model = YOLO('best2.pt')

class VideoStreamConsumer(AsyncWebsocketConsumer):
    last_alert_time = {}
    COOLDOWN_SECONDS = 60

    async def connect(self):
        self.device_id = self.scope['url_route']['kwargs']['device_id']
        self.group_name = f"device_{self.device_id}"

        # Parse query parameters from URL: ws://.../?role=...&token=...&key=...
        query_string = self.scope['query_string'].decode()
        query_params = parse_qs(query_string)
        self.role = query_params.get('role', ['viewer'])[0]
        token_key = query_params.get('token', [None])[0]
        device_key = query_params.get('key', [None])[0]

        # --- Authentication & Ownership Checks ---
        if self.role == 'viewer':
            is_authorized, device_is_online = await self.verify_viewer(token_key, self.device_id)
            if not is_authorized:
                print(f"Unauthorized viewer connection attempt for {self.device_id} (Token: {token_key})")
                await self.close(code=4003)  # Forbidden
                return

            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            print(f"Viewer authorized for device {self.device_id}.")

            # Send current device status to the viewer right away
            initial_status = "online" if device_is_online else "offline"
            await self.send(text_data=json.dumps({"type": "status", "status": initial_status}))

        elif self.role == 'producer':
            is_valid_device = await self.verify_and_set_producer_online(self.device_id, device_key)
            if not is_valid_device:
                print(f"Producer rejected: Device {self.device_id} not recognized or invalid secret key.")
                await self.close(code=4003)
                return

            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            print(f"Producer connected: Device {self.device_id} is now ONLINE.")

            # Notify all connected viewers that the hardware is now online
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "device_status", "status": "online"}
            )
        else:
            await self.close(code=4000)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

        if getattr(self, 'role', None) == 'producer':
            await self.set_producer_offline(self.device_id)
            print(f"Producer disconnected: Device {self.device_id} is now OFFLINE.")

            # Notify viewers that hardware lost connection
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "device_status", "status": "offline"}
            )

    async def receive(self, text_data=None, bytes_data=None):
        # 1. ESP32 (Producer) sends raw video frame
        if bytes_data and self.role == 'producer':
            annotated_frame = await asyncio.to_thread(self.process_frame, bytes_data, self.device_id)
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'video_message', 'bytes': annotated_frame}
            )

        # 2. JSON telemetry or controls
        if text_data:
            data = json.loads(text_data)

            if self.role == 'producer':
                # 1. Save sensor log to database asynchronously
                await self.save_sensor_log(self.device_id, data)
                # Telemetry from ESP32 -> Broadcast to Flutter viewer
                await self.channel_layer.group_send(
                    self.group_name,
                    {'type': 'sensor_message', 'data': data}
                )

            elif self.role == 'viewer':
                # Control command from Flutter -> Relay to ESP32 producer
                await self.channel_layer.group_send(
                    self.group_name,
                    {'type': 'servo_message', 'data': data}
                )

    # --- Channel Layer Handlers ---
    async def video_message(self, event):
        if self.role == 'viewer':
            await self.send(bytes_data=event['bytes'])

    async def sensor_message(self, event):
        if self.role == 'viewer':
            await self.send(text_data=json.dumps({"type": "sensor", "data": event['data']}))

    async def servo_message(self, event):
        if self.role == 'producer':
            await self.send(text_data=json.dumps(event['data']))

    async def device_status(self, event):
        if self.role == 'viewer':
            await self.send(text_data=json.dumps({"type": "status", "status": event['status']}))

    # --- Computer Vision Inference ---
    def process_frame(self, bytes_data, device_id):
        np_arr = np.frombuffer(bytes_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        results = model.track(
            source=frame,
            persist=True,
            tracker="my_botsort.yaml",
            conf=0.15,
            iou=0.5,
            verbose=False
        )

        if results[0].boxes.cls is not None:
            classes = results[0].boxes.cls.int().cpu().tolist()
            if 0 in classes:
                current_time = time.time()
                last_time = VideoStreamConsumer.last_alert_time.get(device_id, 0)
                if current_time - last_time > VideoStreamConsumer.COOLDOWN_SECONDS:
                    print(f"\n🚨 [ALARM] Target detected! Triggering notification for device: {device_id}\n")
                    VideoStreamConsumer.last_alert_time[device_id] = current_time

        annotated_frame = results[0].plot()
        _, buffer = cv2.imencode('.jpg', annotated_frame)
        return buffer.tobytes()

    # --- Database Helpers (Sync to Async) ---
    @database_sync_to_async
    def verify_viewer(self, token_key, device_id):
        if not token_key:
            return False, False
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            device = Device.objects.select_related('owner').get(device_id=device_id)
            # Verify that the token owner is specifically the device owner
            if device.owner_id == token.user_id:
                return True, device.is_online
            return False, False
        except (Token.DoesNotExist, Device.DoesNotExist):
            return False, False

    @database_sync_to_async
    def verify_and_set_producer_online(self, device_id, secret_key):
        try:
            device = Device.objects.get(device_id=device_id)
            if secret_key and str(device.secret_key) != secret_key:
                return False
            device.is_online = True
            device.save(update_fields=['is_online', 'last_seen'])
            return True
        except Device.DoesNotExist:
            return False

    @database_sync_to_async
    def set_producer_offline(self, device_id):
        try:
            device = Device.objects.get(device_id=device_id)
            device.is_online = False
            device.save(update_fields=['is_online', 'last_seen'])
        except Device.DoesNotExist:
            pass


    @database_sync_to_async
    def save_sensor_log(self, device_id, data):
        try:
            device = Device.objects.get(device_id=device_id)
            SensorLog.objects.create(
                device=device,
                ph=data.get('pH'),
                turbidity=data.get('turbidity'),
                temperature=data.get('temperature'),
                weight=data.get('weight')  # <-- Save weight data
            )
        except Device.DoesNotExist:
            pass
    