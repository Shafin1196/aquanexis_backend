import cv2
import numpy as np
import asyncio
import json
import logging
import time
import uuid
from collections import Counter
from datetime import timedelta
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from rest_framework.authtoken.models import Token
from ultralytics import YOLO
from .models import Device, SensorLog, DetectionLog
from notifications.services import send_detection_alert

# best.pt
model = YOLO('best2.pt')
logger = logging.getLogger(__name__)


class VideoStreamConsumer(AsyncWebsocketConsumer):
    last_alert_time = {}
    class_detection_counts = {}
    COOLDOWN_SECONDS = 60
    DETECTION_ALERT_THRESHOLD = 200
    PRODUCER_TIMEOUT_SECONDS = Device.PRODUCER_TIMEOUT_SECONDS
    PRODUCER_WATCHDOG_INTERVAL_SECONDS = 1


    async def connect(self):
        self.device_id = self.scope['url_route']['kwargs']['device_id']
        self.group_name = f"device_{self.device_id}"
        self.connection_id = uuid.uuid4()
        self.latest_detection_counts = []


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
            is_valid_device = await self.verify_and_set_producer_online(
                self.device_id,
                device_key,
                self.connection_id,
            )
            if not is_valid_device:
                print(f"Producer rejected: Device {self.device_id} not recognized or invalid secret key.")
                await self.close(code=4003)
                return


            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            self.producer_watchdog_task = asyncio.create_task(
                self.watch_producer_activity()
            )
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
            watchdog_task = getattr(self, "producer_watchdog_task", None)
            if watchdog_task is not None:
                watchdog_task.cancel()
                await asyncio.gather(watchdog_task, return_exceptions=True)

            changed = await self.set_producer_offline(self.device_id)
            if changed:
                print(f"Producer disconnected: Device {self.device_id} is now OFFLINE.")
                await self.channel_layer.group_send(
                    self.group_name,
                    {"type": "device_status", "status": "offline"}
                )


    async def receive(self, text_data=None, bytes_data=None):
        # 1. ESP32 (Producer) sends raw video frame
        if bytes_data and self.role == 'producer':
            await self.touch_producer_activity(self.device_id)
            (
                annotated_frame,
                detections,
                alert_confidence,
                detection_counts,
            ) = await asyncio.to_thread(
                self.process_frame,
                bytes_data,
                self.device_id,
            )
            self.latest_detection_counts = detection_counts
            await self.save_detection_logs(self.device_id, detections)
            if alert_confidence is not None:
                await self.send_detection_notification(
                    self.device_id,
                    alert_confidence,
                )
            await self.channel_layer.group_send(
                self.group_name,
                {'type': 'video_message', 'bytes': annotated_frame}
            )


        # 2. JSON telemetry or controls
        if text_data:
            data = json.loads(text_data)


            if self.role == 'producer':
                data["detections"] = self.latest_detection_counts
                # logger.info(
                #     "Sensor JSON received from device %s: %s",
                #     self.device_id,
                #     data,
                # )
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


        result = results[0]
        boxes = result.boxes
        detections = []
        alert_confidence = None
        detection_class_ids = []

        if boxes.cls is not None:
            class_ids = boxes.cls.int().cpu().tolist()
            confidences = boxes.conf.cpu().tolist()
            coordinates = boxes.xyxy.cpu().tolist()
            track_ids = (
                boxes.id.int().cpu().tolist()
                if boxes.id is not None
                else [None] * len(class_ids)
            )

            for class_id, confidence, coordinate, track_id in zip(
                class_ids,
                confidences,
                coordinates,
                track_ids,
            ):
                if confidence < 0.5:
                    continue

                x1, y1, x2, y2 = coordinate
                detections.append({
                    "class_id": class_id,
                    "class_name": model.names[class_id],
                    "confidence": confidence,
                    "track_id": track_id,
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                })
                detection_class_ids.append(class_id)

            if any(
                class_id == 0 and confidence >= 0.5
                for class_id, confidence in zip(class_ids, confidences)
            ):
                alert_confidence = max(
                    confidence
                    for class_id, confidence in zip(class_ids, confidences)
                    if class_id == 0 and confidence >= 0.5
                )
                class_0_count = sum(
                    class_id == 0 and confidence >= 0.5
                    for class_id, confidence in zip(class_ids, confidences)
                )
                detection_count = (
                    VideoStreamConsumer.class_detection_counts.get(device_id, 0)
                    + class_0_count
                )

                if detection_count >= VideoStreamConsumer.DETECTION_ALERT_THRESHOLD:
                    current_time = time.time()
                    print(
                        f"\n🚨 [ALARM] Class 0 detected "
                        f"{VideoStreamConsumer.DETECTION_ALERT_THRESHOLD} times "
                        f"for device: {device_id}\n"
                    )
                    VideoStreamConsumer.class_detection_counts[device_id] = 0
                    VideoStreamConsumer.last_alert_time[device_id] = current_time
                else:
                    VideoStreamConsumer.class_detection_counts[device_id] = detection_count

                    current_time = time.time()
                    last_time = VideoStreamConsumer.last_alert_time.get(device_id, 0)
                    if current_time - last_time > VideoStreamConsumer.COOLDOWN_SECONDS:
                        print(
                            f"\n🚨 [ALARM] Abnormal activity detected! "
                            f"Triggering notification for device: {device_id}\n"
                        )
                        VideoStreamConsumer.last_alert_time[device_id] = current_time
                    else:
                        alert_confidence = None


        annotated_frame = result.plot()
        _, buffer = cv2.imencode('.jpg', annotated_frame)
        class_counts = Counter(detection_class_ids)
        detection_counts = [
            {
                "class_id": class_id,
                "class_name": model.names[class_id],
                "count": count,
            }
            for class_id, count in sorted(class_counts.items())
        ]
        return (
            buffer.tobytes(),
            detections,
            alert_confidence,
            detection_counts,
        )


    # --- Database Helpers (Sync to Async) ---
    async def watch_producer_activity(self):
        try:
            while True:
                await asyncio.sleep(self.PRODUCER_WATCHDOG_INTERVAL_SECONDS)
                changed = await self.set_stale_producer_offline(self.device_id)
                if changed:
                    print(
                        f"Producer timed out: Device {self.device_id} is now OFFLINE."
                    )
                    await self.channel_layer.group_send(
                        self.group_name,
                        {"type": "device_status", "status": "offline"}
                    )
                    return
        except asyncio.CancelledError:
            raise

    @database_sync_to_async
    def verify_viewer(self, token_key, device_id):
        if not token_key:
            return False, False
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            Device.mark_stale_devices_offline()
            device = Device.objects.select_related('owner').get(device_id=device_id)
            # Verify that the token owner is specifically the device owner
            if device.owner_id == token.user_id:
                return True, device.is_online
            return False, False
        except (Token.DoesNotExist, Device.DoesNotExist):
            return False, False


    @database_sync_to_async
    def verify_and_set_producer_online(self, device_id, secret_key, connection_id):
        try:
            device = Device.objects.get(device_id=device_id)
            if secret_key and str(device.secret_key) != secret_key:
                return False
            device.is_online = True
            device.producer_connection_id = connection_id
            device.save(update_fields=['is_online', 'last_seen', 'producer_connection_id'])
            return True
        except Device.DoesNotExist:
            return False


    @database_sync_to_async
    def set_producer_offline(self, device_id):
        return Device.objects.filter(
            device_id=device_id,
            producer_connection_id=self.connection_id,
            is_online=True,
        ).update(
            is_online=False,
            producer_connection_id=None,
        ) > 0

    @database_sync_to_async
    def set_stale_producer_offline(self, device_id):
        cutoff = timezone.now() - timedelta(
            seconds=self.PRODUCER_TIMEOUT_SECONDS
        )
        return Device.objects.filter(
            device_id=device_id,
            producer_connection_id=self.connection_id,
            is_online=True,
            last_seen__lt=cutoff,
        ).update(
            is_online=False,
            producer_connection_id=None,
        ) > 0

    @database_sync_to_async
    def touch_producer_activity(self, device_id):
        Device.objects.filter(
            device_id=device_id,
            producer_connection_id=self.connection_id,
            is_online=True,
        ).update(last_seen=timezone.now())

    @database_sync_to_async
    def save_detection_logs(self, device_id, detections):
        if not detections:
            return

        device_query = Device.objects.filter(device_id=device_id)
        connection_id = getattr(self, "connection_id", None)
        if connection_id is not None:
            device_query = device_query.filter(
                producer_connection_id=connection_id,
            )
        device = device_query.get()

        DetectionLog.objects.bulk_create([
            DetectionLog(
                device=device,
                class_id=detection["class_id"],
                class_name=detection["class_name"],
                confidence=detection["confidence"],
                track_id=detection["track_id"],
                x1=detection["x1"],
                y1=detection["y1"],
                x2=detection["x2"],
                y2=detection["y2"],
            )
            for detection in detections
        ])

    @database_sync_to_async
    def send_detection_notification(self, device_id, confidence):
        try:
            device = Device.objects.select_related("owner").get(
                device_id=device_id,
            )
        except Device.DoesNotExist:
            logger.error(
                "Cannot send detection alert: device %s does not exist.",
                device_id,
            )
            return

        if device.owner is None:
            logger.warning(
                "Cannot send detection alert for device %s: no owner.",
                device_id,
            )
            return

        try:
            results = send_detection_alert(
                user=device.owner,
                device_id=device_id,
                confidence=confidence,
            )
        except Exception:
            logger.exception(
                "FCM detection alert failed for device %s.",
                device_id,
            )
            return

        logger.info("FCM detection alert result for device %s: %s", device_id, results)



    @database_sync_to_async
    def save_sensor_log(self, device_id, data):
        try:
            connection_id = getattr(self, "connection_id", None)
            device_query = Device.objects.filter(device_id=device_id)
            if connection_id is not None:
                device_query = device_query.filter(producer_connection_id=connection_id)
            device = device_query.get()
            ph = data.get('pH')
            turbidity = data.get('turbidity_voltage', data.get('turbidity'))
            temperature = data.get('temperature')
            weight = data.get('weight_grams', data.get('weight'))
            # logger.info(
            #     "Sensor values extracted for device %s: pH=%r, "
            #     "temperature=%r, turbidity=%r, weight=%r; JSON keys=%s; "
            #     "payload=%r",
            #     device_id,
            #     ph,
            #     temperature,
            #     turbidity,
            #     weight,
            #     list(data.keys()),
            #     data,
            # )
            if all(value is None for value in (ph, turbidity, temperature, weight)):
                # logger.info(
                #     "Skipping empty sensor log for device %s",
                #     device_id,
                # )
                device.save(update_fields=['is_online', 'last_seen'])
                return

            sensor_log = SensorLog.objects.create(
                device=device,
                ph=ph,
                turbidity=turbidity,
                temperature=temperature,
                weight=weight,
            )
            # logger.info(
            #     "Sensor data saved for device %s: temperature=%s, "
            #     "turbidity=%s, weight=%s",
            #     device_id,
            #     sensor_log.temperature,
            #     sensor_log.turbidity,
            #     sensor_log.weight,
            # )
            device.save(update_fields=['is_online', 'last_seen'])
        except Device.DoesNotExist:
            pass
   
