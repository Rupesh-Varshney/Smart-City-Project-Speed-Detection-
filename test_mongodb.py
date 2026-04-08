from pymongo import MongoClient
from datetime import datetime

# Your MongoDB URL
MONGO_URL = "mongodb+srv://gr1763_db_user:9528850770@cluster0.xuh8hky.mongodb.net/vehicleDB?retryWrites=true&w=majority&appName=Cluster0"

# Connect
client = MongoClient(MONGO_URL)

# Access DB
db = client["vehicleDB"]

# Access Collection
collection = db["vehicle_log"]

# Insert test data
test_data = {
    "vehicle_id": 1,
    "category": "Car",
    "date": datetime.now().strftime("%Y-%m-%d"),
    "time": datetime.now().strftime("%H:%M:%S"),
    "speed": 45.6
}

collection.insert_one(test_data)

print("✅ Data Stored Successfully!")