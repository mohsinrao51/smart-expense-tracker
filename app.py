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
import calendar
from collections import defaultdict


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

    # ---- Category breakdown (for the coin wheel + ledger bars) ----
    # Top 5 expense categories by amount; anything beyond that is
    # folded into "Other" so the wheel never gets more slices than
    # it can show cleanly.
    category_totals = defaultdict(int)

    for txn in data:
        if txn["type"] == "expense":
            category_totals[txn["category"]] += txn["amount"]

    sorted_categories = sorted(
        category_totals.items(),
        key=lambda item: item[1],
        reverse=True
    )

    MAX_CATEGORIES = 5

    top_categories = sorted_categories[:MAX_CATEGORIES]
    other_total = sum(
        amount for _, amount in sorted_categories[MAX_CATEGORIES:]
    )

    category_data = [
        {"category": cat, "amount": amount}
        for cat, amount in top_categories
    ]

    if other_total > 0:
        category_data.append({"category": "Other", "amount": other_total})

    category_total = sum(c["amount"] for c in category_data)

    for c in category_data:
        c["percent"] = round(
            (c["amount"] / category_total * 100) if category_total else 0,
            1
        )

    # ---- Monthly income vs expense trend (last 6 months) ----
    now = get_user_time()

    months = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))

    monthly_totals = {
        month: {"income": 0, "expense": 0}
        for month in months
    }

    for txn in data:
        key = (txn["date"].year, txn["date"].month)
        if key in monthly_totals:
            monthly_totals[key][txn["type"]] += txn["amount"]

    trend_data = [
        {
            "label": f"{calendar.month_abbr[m]} {y}",
            "income": monthly_totals[(y, m)]["income"],
            "expense": monthly_totals[(y, m)]["expense"]
        }
        for (y, m) in months
    ]

    return render_template(
        "dashboard.html",
            name=user["name"],
            income=income,
            expense=expense,
            balance=income-expense,
            transactions=data,
            category_data=category_data,
            category_total=category_total,
            trend_data=trend_data
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

    # Values echoed back to the template so the form
    # keeps showing what the user selected/entered.
    start_date_val = request.form.get("start_date", "")
    end_date_val = request.form.get("end_date", "")

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

        # txn["date"] comes back from MongoDB as a naive UTC datetime
        # (Mongo drops tzinfo on save), so this comparison value must
        # also be naive UTC or Python raises a TypeError.
        seven_days = (
            get_user_time() - timedelta(days=7)
        ).astimezone(pytz.utc).replace(tzinfo=None)

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

    # Custom Date Range
    elif report_type == "custom":

        if not start_date_val or not end_date_val:
            return render_template(
                "reports.html",
                transactions=[],
                income=0,
                expense=0,
                balance=0,
                report_type=report_type,
                start_date=start_date_val,
                end_date=end_date_val,
                error="Please select both a start and end date."
            )

        tz = pytz.timezone(
            session.get("timezone", "Asia/Karachi")
        )

        try:
            # Build the range in the user's local timezone first,
            # then convert to naive UTC to match how txn["date"] is
            # actually stored/returned by MongoDB.
            start_date = tz.localize(
                datetime.strptime(start_date_val, "%Y-%m-%d")
            ).astimezone(pytz.utc).replace(tzinfo=None)

            # Include the entire end day (up to 23:59:59)
            end_date = (
                tz.localize(
                    datetime.strptime(end_date_val, "%Y-%m-%d")
                ) + timedelta(days=1, seconds=-1)
            ).astimezone(pytz.utc).replace(tzinfo=None)

        except ValueError:
            return render_template(
                "reports.html",
                transactions=[],
                income=0,
                expense=0,
                balance=0,
                report_type=report_type,
                start_date=start_date_val,
                end_date=end_date_val,
                error="Invalid date format."
            )

        if start_date > end_date:
            return render_template(
                "reports.html",
                transactions=[],
                income=0,
                expense=0,
                balance=0,
                report_type=report_type,
                start_date=start_date_val,
                end_date=end_date_val,
                error="Start date must be before end date."
            )

        data = [
            txn for txn in data
            if start_date <= txn["date"] <= end_date
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
        balance=income-expense,
        report_type=report_type,
        start_date=start_date_val,
        end_date=end_date_val
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
