from flask import Flask, Response
import cv2
from ultralytics import YOLO
from pymongo import MongoClient
from datetime import datetime
import threading
import requests
import numpy as np
import time

# ================= SETTINGS =================
VIDEO_URL = "http://10.103.145.61:5000" 
MODEL_PATH = "yolov8n.pt"

DISTANCE_THRESHOLD = 60
MEMORY_DISTANCE = 80
MEMORY_TIME = 10

FPS = 15
PIXELS_PER_METER = 120

# ================= MongoDB =================
MONGO_URL = "mongodb+srv://gr1763_db_user:9528850770@cluster0.xuh8hky.mongodb.net/vehicleDB?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(MONGO_URL)
db = client["vehicleDB"]
collection = db["vehicle_log"]

# ================= APP =================
app = Flask(__name__)
model = YOLO(MODEL_PATH)

category_map = {
    "car": "Car",
    "motorcycle": "Motorcycle",
    "bus": "Bus",
    "truck": "Truck"
}

# ================= GLOBALS =================
last_vehicle = collection.find_one(sort=[("vehicle_id", -1)])
next_vehicle_id = last_vehicle["vehicle_id"] if last_vehicle else 0

tracked_objects = {}
already_logged = {}
previous_frame = {}
max_speed_memory = {}

frame_count = 0

latest_frame = None
annotated_frame = None
lock = threading.Lock()

# ================= STREAM FIX =================
def stream_frames():
    while True:
        try:
            stream = requests.get(VIDEO_URL, stream=True, timeout=5)
            bytes_data = b''

            for chunk in stream.iter_content(chunk_size=1024):
                bytes_data += chunk
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')

                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]

                    frame = cv2.imdecode (
                        np.frombuffer(jpg, dtype=np.uint8),
                        cv2.IMREAD_COLOR

                    
                    )
                    frame = cv2.resize(frame, (1280, 720))   # 🔥 Upscale to 720p


                    yield frame
        except:
            print("Reconnecting to stream...")
            time.sleep(1)

# ================= HELPER =================
def get_center(x1,y1,x2,y2):
    return int((x1+x2)/2), int((y1+y2)/2)

# ================= YOLO THREAD =================
def yolo_detection():
    global latest_frame, annotated_frame, next_vehicle_id, frame_count

    while True:
        if latest_frame is None:
            time.sleep(0.01)
            continue

        frame_count += 1

        # 🔥 SKIP FRAMES (performance boost)
        if frame_count % 3 != 0:
            continue

        frame_copy = latest_frame.copy()
        results = model(frame_copy, conf=0.4, verbose=False)

        for result in results:
            for box in result.boxes:

                cls = int(box.cls[0])
                label = model.names[cls]

                if label in category_map:

                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    category = category_map[label]
                    cx, cy = get_center(x1,y1,x2,y2)

                    same_object = False
                    object_id = None

                    for id, pt in tracked_objects.items():
                        dist = ((cx-pt[0])**2 + (cy-pt[1])**2) ** 0.5
                        if dist < DISTANCE_THRESHOLD:
                            same_object = True
                            object_id = id
                            tracked_objects[id] = (cx,cy)
                            break

                    if not same_object:
                        for id, data in already_logged.items():
                            prev_pt, timestamp = data
                            dist = ((cx-prev_pt[0])**2 + (cy-prev_pt[1])**2) ** 0.5
                            if dist < MEMORY_DISTANCE:
                                same_object = True
                                object_id = id
                                tracked_objects[id] = (cx,cy)
                                break

                    if not same_object:
                        next_vehicle_id += 1
                        object_id = next_vehicle_id

                        tracked_objects[object_id] = (cx,cy)
                        already_logged[object_id] = ((cx,cy), datetime.now())

                        now = datetime.now()

                        # 🔥 NON-BLOCKING DB WRITE
                        threading.Thread(target=collection.insert_one, args=({
                            "vehicle_id": object_id,
                            "category": category,
                            "date": now.strftime("%Y-%m-%d"),
                            "time": now.strftime("%H:%M:%S")
                        },)).start()

                    # ================= SPEED =================
                    speed = 0

                    if object_id not in previous_frame:
                        previous_frame[object_id] = (cx, cy, frame_count)
                    else:
                        px, py, prev_frame_id = previous_frame[object_id]

                        pixel_distance = ((cx-px)**2 + (cy-py)**2) ** 0.5
                        frame_diff = frame_count - prev_frame_id

                        if frame_diff > 0:
                            real_distance = (pixel_distance / PIXELS_PER_METER)*4
                            time_elapsed = frame_diff / FPS

                            if time_elapsed > 0:
                                speed = (real_distance / time_elapsed) * 3.6

                                if 0 < speed < 200:
                                    if object_id not in max_speed_memory or speed > max_speed_memory[object_id]:
                                        max_speed_memory[object_id] = speed

                                        threading.Thread(target=collection.update_one, args=(
                                            {"vehicle_id": object_id},
                                            {"$set": {"speed": round(speed,2)}}
                                        )).start()

                        previous_frame[object_id] = (cx, cy, frame_count)

                    # DRAW
                    cv2.rectangle(frame_copy, (x1,y1), (x2,y2), (0,255,0), 2)
                    cv2.putText(frame_copy,
                                f"ID:{object_id} {category} {round(max_speed_memory.get(object_id,0),1)} km/h",
                                (x1, y1-10),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7,
                                (0,255,0),
                                2)

        # CLEAN MEMORY
        current_time = datetime.now()
        for vid in list(already_logged.keys()):
            if (current_time - already_logged[vid][1]).seconds > MEMORY_TIME:
                del already_logged[vid]

        with lock:
            annotated_frame = frame_copy

        time.sleep(0.01)

# START YOLO THREAD
threading.Thread(target=yolo_detection, daemon=True).start()

# ================= STREAM =================
def generate_frames():
    global latest_frame, annotated_frame

    for frame in stream_frames():
        if frame is None:
            continue

        latest_frame = frame

        with lock:
            display_frame = annotated_frame if annotated_frame is not None else frame

        ret, buffer = cv2.imencode('.jpg', display_frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ================= RUN =================
if __name__ == "__main__":
    print("🚀 Server started at http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, threaded=True)