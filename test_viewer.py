import cv2, asyncio, websockets, json, numpy as np

async def view():
    uri = "ws://127.0.0.1:8000/ws/device/esp_p4_001/?role=viewer&token=f5c105170a2d7b28b5be1fd77cec4fb58225d72f"
    
    async with websockets.connect(uri) as ws:
        # Simulate a user sliding the servo control every 5 seconds
        async def mock_flutter_slider():
            while True:
                await asyncio.sleep(5)
                await ws.send(json.dumps({"action": "servo", "angle": 90}))
                
        asyncio.create_task(mock_flutter_slider())
        
        print("Flutter App Online. Watching stream...")
        while True:
            message = await ws.recv()
            
            if isinstance(message, bytes): # It's a video frame
                np_arr = np.frombuffer(message, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                cv2.imshow("Flutter Live Dashboard", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
            else: # It's a JSON string
                print("App received sensor telemetry:", message)

asyncio.run(view())