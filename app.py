from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient

app = Flask(__name__)

# MongoDB Connection
client = MongoClient("mongodb+srv://gr1763_db_user:9528850770@cluster0.xuh8hky.mongodb.net/vehicleDB?retryWrites=true&w=majority&appName=Cluster0")
db = client["vehicleDB"]
collection = db["vehicle_log"]

print("Total Records:", collection.count_documents({}))
#print(list(collection.find({"speed": {"$gt": 50}})))

# ================= DASHBOARD PAGE =================
@app.route('/')
def home():
    return render_template('dashboard.html')   


# ================= ALERTS (>50 SPEED) =================
@app.route('/api/alerts')
def get_alerts():
    alerts = list(collection.find(
        {
            "speed": {
                "$exists": True,
                "$ne": 0,
                "$gt": 50
            }
        },
        {
            "_id": 0
        }
    ))
    return jsonify(alerts)

# ================= TOTAL VEHICLES =================
@app.route('/api/total')
def total_vehicles():
    total = collection.count_documents({})
    return jsonify({"total": total})

# ================= ALL VEHICLES =================
@app.route('/api/vehicles')
def all_vehicles():
    data = list(collection.find({}, {"_id": 0})
                .sort([("date", -1), ("time", -1)])
                .limit(100))
    return jsonify(data)

# ================= FILTER DATA =================
@app.route('/api/filter')
def filter_data():
    query = {}

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    category = request.args.get("category")

    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    if category and category != "All":
        query["category"] = category

    data = list(collection.find(query, {"_id": 0})
                .sort([("date", -1), ("time", -1)]))

    return jsonify(data)

# ================= HOURLY ACTIVITY =================
@app.route('/api/hourly')
def hourly_activity():
    pipeline = [
        {
            "$group": {
                "_id": {"$substr": ["$time", 0, 2]},
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id": 1}}
    ]

    data = list(collection.aggregate(pipeline))
    return jsonify(data)

# ================= RUN APP =================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)