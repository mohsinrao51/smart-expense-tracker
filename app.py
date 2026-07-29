#from flask import Flask, request, jsonify

from flask import Flask, request, jsonify, render_template, session, redirect
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from flask import send_file
from reportlab.pdfgen import canvas
import io
import pytz


app = Flask(__name__)
app.secret_key = "mohsin-secret-key"

def get_user_time():
    return datetime.now(
        pytz.timezone(
            session.get(
                "timezone",
                "Asia/Karachi"
            )
        )
    )
app.permanent_session_lifetime = timedelta(
    minutes=5
)

# MongoDB Connection
app.config["MONGO_URI"] = "mongodb://localhost:27017/expense_tracker"

mongo = PyMongo(app)

# Collections
users = mongo.db.users
transactions = mongo.db.transactions


# Home Route
@app.route("/")
def home():
    return redirect("/login-ui")


# Register User
@app.route("/register", methods=["POST"])
def register():

    data = request.json

    if users.find_one({"email": data["email"]}):
        return jsonify({"message": "User already exists"}), 400

    user = {
        "name": data["name"],
        "email": data["email"],
        "password": generate_password_hash(data["password"])
    }

    users.insert_one(user)

    return jsonify({"message": "User registered successfully"}), 201


# Login User
@app.route("/login", methods=["POST"])
def login():

    data = request.json

    user = users.find_one({"email": data["email"]})

    if user and check_password_hash(user["password"], data["password"]):
        return jsonify({"message": "Login Successful"})

    return jsonify({"message": "Invalid Credentials"}), 401


# Add Transaction
@app.route("/transaction", methods=["POST"])
def add_transaction():

    data = request.json
    print("Current User Time:", get_user_time())
    print("Timezone:", session["timezone"])

    transaction = {
        "user_id": user_id,
        "type": request.form["type"],
        "amount": int(request.form["amount"]),
        "category": request.form["category"],
        "description": request.form["description"],
        "date": get_user_time()
    }

    transactions.insert_one(transaction)

    return jsonify({"message": "Transaction Added"}), 201


# Get All Transactions
@app.route("/transactions/<user_id>", methods=["GET"])
def get_transactions(user_id):

    result = []

    for txn in transactions.find({"user_id": user_id}):

        result.append({
            "id": str(txn["_id"]),
            "type": txn["type"],
            "amount": txn["amount"],
            "category": txn["category"],
            "description": txn["description"],
            "date": txn["date"]
        })

    return jsonify(result)

@app.route("/register-ui", methods=["GET", "POST"])
def register_ui():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return render_template(
                "register.html",
                error="Passwords do not match!"
            )

        if users.find_one({"email": email}):
            return render_template(
                "register.html",
                error="Email already exists!"
            )

        users.insert_one({
                "name": name,
                "email": email,
                "password": generate_password_hash(password),
                "timezone": "Asia/Karachi"
            })

        return redirect("/login-ui")

    return render_template("register.html")


@app.route("/login-ui", methods=["GET", "POST"])
def login_ui():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = users.find_one({"email": email})

        if user and check_password_hash(
            user["password"], password):
            session.permanent = False

            session["user_id"] = str(user["_id"])
            session["timezone"] = user.get(
                "timezone",
                "Asia/Karachi"
            )                  
            return redirect("/dashboard-ui")
        
        

        return render_template(
            "login.html",
            error="Invalid Email or Password!"
        )

    return render_template("login.html")



# Dashboard
@app.route("/dashboard-ui")
def dashboard_ui():

    if "user_id" not in session:
        return redirect("/login-ui")

    user_id = session["user_id"]

    data = list(
        transactions.find({"user_id": user_id})
    )

    income = sum(
        txn["amount"] for txn in data
        if txn["type"] == "income"
    )

    expense = sum(
        txn["amount"] for txn in data
        if txn["type"] == "expense"
    )


    user = users.find_one(
        {"_id": ObjectId(user_id)}
    )

    return render_template(
        "dashboard.html",
            name=user["name"],
            income=income,
            expense=expense,
            balance=income-expense,
            transactions=data
    )


#Report Module
@app.route("/reports-ui")
def reports_ui():

    if "user_id" not in session:
        return redirect("/login-ui")

    user_id = session["user_id"]

    data = list(
        transactions.find({"user_id": user_id})
    )

    income = sum(
        txn["amount"] for txn in data
        if txn["type"] == "income"
    )

    expense = sum(
        txn["amount"] for txn in data
        if txn["type"] == "expense"
    )

    return render_template(
        "reports.html",
        income=income,
        expense=expense,
        balance=income-expense,
        transactions=data
    )

@app.route("/generate-report", methods=["POST"])
def generate_report():

    if "user_id" not in session:
        return redirect("/login-ui")

    user_id = session["user_id"]

    report_type = request.form["report_type"]

    data = list(
        transactions.find({"user_id": user_id})
    )

    # Monthly
    if report_type == "monthly":

        current_month = get_user_time().month

        data = [
            txn for txn in data
            if txn["date"].month == current_month
        ]

    # Weekly
    elif report_type == "weekly":

        seven_days = get_user_time() - timedelta(days=7)

        data = [
            txn for txn in data
            if txn["date"] >= seven_days
        ]

    # Yearly
    elif report_type == "yearly":

        current_year = get_user_time().year

        data = [
            txn for txn in data
            if txn["date"].year == current_year
        ]

    income = sum(
        txn["amount"]
        for txn in data
        if txn["type"] == "income"
    )

    expense = sum(
        txn["amount"]
        for txn in data
        if txn["type"] == "expense"
    )

    return render_template(
        "reports.html",
        transactions=data,
        income=income,
        expense=expense,
        balance=income-expense
    )

@app.route("/export-pdf")
def export_pdf():

    if "user_id" not in session:
        return redirect("/login-ui")

    user_id = session["user_id"]

    user = users.find_one(
        {"_id": ObjectId(user_id)}
    )

    data = list(
        transactions.find({"user_id": user_id})
    )

    income = sum(
        txn["amount"]
        for txn in data
        if txn["type"] == "income"
    )

    expense = sum(
        txn["amount"]
        for txn in data
        if txn["type"] == "expense"
    )

    balance = income - expense

    buffer = io.BytesIO()

    pdf = canvas.Canvas(buffer)

    pdf.drawString(
        100,
        800,
        "Smart Expense Tracker"
    )

    pdf.drawString(
        100,
        780,
        f"Generated: {get_user_time().strftime('%d-%b-%Y %I:%M %p')}"
    )

    pdf.drawString(
        100,
        760,
        f"User: {user['name']}"
    )

    pdf.drawString(
        100,
        740,
        f"Total Income: PKR {income}"
    )

    pdf.drawString(
        100,
        720,
        f"Total Expense: PKR {expense}"
    )

    pdf.drawString(
        100,
        700,
        f"Current Balance: PKR {balance}"
    )

    pdf.drawString(
        100,
        670,
        "Transactions"
    )

    y = 650

    for txn in data:

        pdf.drawString(

            100,
            y,

            f"{txn['date'].strftime('%d-%b-%Y')} | "
            f"{txn['type']} | "
            f"{txn['category']} | "
            f"PKR {txn['amount']}"

        )

        y -= 20

        # New page if PDF becomes full
        if y < 50:

            pdf.showPage()

            y = 800

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="financial_report.pdf",
        mimetype="application/pdf"
    )
@app.route("/transactions-ui", methods=["GET", "POST"])
def transactions_ui():

    if "user_id" not in session:
        return redirect("/login-ui")

    user_id = session["user_id"]

    if request.method == "POST":

        transaction = {
            "user_id": user_id,
            "type": request.form["type"],
            "amount": int(request.form["amount"]),
            "category": request.form["category"],
            "description": request.form.get(
                "description", ""
            ),
            "date": get_user_time()
        }

        transactions.insert_one(transaction)

    data = list(
        transactions.find({"user_id": user_id})
    )

    income = sum(
        txn["amount"] for txn in data
        if txn["type"] == "income"
    )

    expense = sum(
        txn["amount"] for txn in data
        if txn["type"] == "expense"
    )

    return render_template(
        "transactions.html",
        transactions=data,
        income=income,
        expense=expense,
        balance=income-expense
    )

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login-ui")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
