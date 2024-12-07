from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_mail import Mail, Message
from twilio.rest import Client
from datetime import datetime, timedelta
from models import db, User, Meal, Reservation, Feedback, Order
import os
from flask_cors import CORS  # Import CORS
from flask_migrate import Migrate  # Import Migrate

# Initialize app, mail, JWT, and CORS
app = Flask(__name__)
app.config.from_object('config.Config')

# Enable CORS
CORS(app, origins="*", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])  # Allow all origins, you can specify specific ones if needed

db.init_app(app)
jwt = JWTManager(app)
mail = Mail(app)

# Twilio Client setup
twilio_client = Client(app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN'])

# Initialize Flask-Migrate
migrate = Migrate(app, db)  # Initialize migration tool

# Create the database schema (migrations will handle schema changes after this)
with app.app_context():
    db.create_all()

# Function to send email notifications
def send_email(subject, recipient, body):
    msg = Message(subject, recipients=[recipient])
    msg.body = body
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Error sending email: {e}")

# Function to send SMS notifications
def send_sms(body, recipient):
    try:
        message = twilio_client.messages.create(
            body=body,
            from_=app.config['TWILIO_PHONE_NUMBER'],
            to=recipient
        )
        print(f"SMS sent: {message.sid}")
    except Exception as e:
        print(f"Error sending SMS: {e}")

# Register endpoint for new users
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    password = data['password']
    role = data['role']
    
    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "User already exists"}), 400
    
    new_user = User(username=username, password=password, role=role)
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({"msg": "User registered successfully"}), 201

# Login endpoint to get JWT
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data['username']
    password = data['password']
    
    user = User.query.filter_by(username=username, password=password).first()
    if user:
        token = create_access_token(identity=username)
        return jsonify({"msg": "Login successful", "token": token}), 200
    else:
        return jsonify({"msg": "Invalid credentials"}), 401

# Endpoint to create a new reservation (includes sending confirmation email and SMS)
@app.route('/user/reservations', methods=['POST'])
@jwt_required()
def book_reservation():
    current_user = get_jwt_identity()
    user = User.query.filter_by(username=current_user).first()
    
    data = request.get_json()
    check_in = datetime.strptime(data['check_in'], '%Y-%m-%d %H:%M:%S')
    check_out = datetime.strptime(data['check_out'], '%Y-%m-%d %H:%M:%S')
    
    reservation = Reservation(check_in=check_in, check_out=check_out, user_id=user.id)
    db.session.add(reservation)
    db.session.commit()

    # Send email confirmation
    send_email(
        subject="Reservation Confirmation",
        recipient=user.username,  # Assuming email is same as username
        body=f"Your reservation is confirmed! Check-in: {check_in}, Check-out: {check_out}."
    )
    
    # Send SMS confirmation
    send_sms(
        body=f"Reservation confirmed! Check-in: {check_in}, Check-out: {check_out}.",
        recipient=data['phone_number']  # Assuming user provides phone number in data
    )
    
    return jsonify({"msg": "Reservation made successfully"}), 201

# Endpoint for reminders (e.g., 1 day before check-in)
@app.route('/user/reminders', methods=['GET'])
@jwt_required()
def send_reminders():
    current_user = get_jwt_identity()
    user = User.query.filter_by(username=current_user).first()
    
    reservations = Reservation.query.filter_by(user_id=user.id).all()
    for reservation in reservations:
        if reservation.check_in - datetime.now() <= timedelta(days=1):
            # Send reminder email
            send_email(
                subject="Reservation Reminder",
                recipient=user.username,
                body=f"Reminder: Your reservation is tomorrow. Check-in: {reservation.check_in}, Check-out: {reservation.check_out}."
            )
            # Send reminder SMS
            send_sms(
                body=f"Reminder: Your reservation is tomorrow. Check-in: {reservation.check_in}, Check-out: {reservation.check_out}.",
                recipient=user.username  # Assuming phone number is the same as username
            )
    
    return jsonify({"msg": "Reminders sent."}), 200

# Endpoint to submit feedback
@app.route('/user/feedback', methods=['POST'])
@jwt_required()
def submit_feedback():
    current_user = get_jwt_identity()
    user = User.query.filter_by(username=current_user).first()
    
    data = request.get_json()
    feedback = Feedback(content=data['content'], rating=data['rating'], user_id=user.id, meal_id=data.get('meal_id'))
    db.session.add(feedback)
    db.session.commit()
    
    # Send feedback confirmation email
    send_email(
        subject="Feedback Submitted",
        recipient=user.username,
        body=f"Thank you for your feedback: {data['content']}. We appreciate your input!"
    )
    
    return jsonify({"msg": "Feedback submitted successfully"}), 201

if __name__ == '__main__':
    app.run(debug=True)

