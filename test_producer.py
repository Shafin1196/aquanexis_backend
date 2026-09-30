import cv2, asyncio, websockets, json

async def stream():
    uri = "ws://192.168.0.113:8000/ws/device/esp_p4_001/?role=producer&key=a4ef63f7-697f-4e65-8fa5-0b7b13fe7a5e"
    cap = cv2.VideoCapture("test.mp4") # Or 0 for webcam
    
    async with websockets.connect(uri) as ws:
        # Listen for servo commands from Flutter in the background
        async def listen_for_commands():
            while True:
                print("Hardware received command:", await ws.recv())
                
        asyncio.create_task(listen_for_commands())
        
        print("Hardware Online. Streaming video and sensors...")
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            await ws.send(buffer.tobytes()) # Send Video
            await ws.send(json.dumps({"pH": 7.2, "turbidity": 12})) # Send Sensors
            
            await asyncio.sleep(0.05) 

asyncio.run(stream())
