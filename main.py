from flask import Flask, render_template, request, flash, redirect, url_for, session, abort, make_response, jsonify, send_file
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from functools import wraps
import mysql.connector, database
# from reportlab.lib.pagesizes import letter
from passlib.hash import sha256_crypt

conn = database.getConnection() # connection to DB

app = Flask(__name__)
app.secret_key = '5012'

PLANE_CAPACITY = 130

def check_booking_validity():

    today = date.today()

    dbcursor = conn.cursor()
    SELECT_statement = "SELECT bookingID, ticket_date FROM bookings"
    dbcursor.execute(SELECT_statement)
    booking_info = dbcursor.fetchall()

    for entered_dates in booking_info:
        booking_id = entered_dates[0]
        ticket_date = entered_dates[1]
        # dates = datetime.strptime(ticket_date, "%Y-%m-%d").date()
        if ticket_date < today:
            UPDATE_statement = """
                UPDATE bookings
                SET statusID = 1
                WHERE bookingID = %s
            """
            dbcursor.execute(UPDATE_statement, (booking_id,))
            conn.commit()

            delete_statement = "DELETE FROM route_capacity WHERE ticket_date = %s"
            dbcursor.execute(delete_statement, (ticket_date,))


# homepage
@app.route('/')
@app.route('/home')
@app.route('/home.html')
def home():
    check_booking_validity()
    return render_template('home.html')

@app.route('/navbar')
def navbar():
    if not session or 'email' not in session or 'admin' not in session:
    # if session['email'] == '' or session['name'] == '':
        return render_template('nav.html')
    # else:
    return render_template('nav.html', name=session['name'], user=session['email'], admin=session['admin'])


@app.route('/cookies')
def cookies():
    return render_template('cookies.html')


# for pages where login is required such as booking a flight
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('email'):
            flash("You need to be signed in to make a booking.", "warning")
            # you can pass next so you can return after login
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated


# to retreive travel options for the chosen departure city, used in booking page
@app.route('/get-travel-options', methods=['GET'])
def get_travel_options():
    cursor = conn.cursor()

    TABLE_NAME = 'routes'
    SELECT_statement = f"SELECT departure_city, arrival_city FROM {TABLE_NAME}"
    
    cursor.execute(SELECT_statement)
    rows = cursor.fetchall()

    # Convert database rows into JSON format
    travel_data = [{"departure": row[0], "arrival": row[1]} for row in rows]

    return jsonify(travel_data)


# renders the page that shows options for users to manage their account
@app.route('/account', methods = ['POST', 'GET'])
@app.route('/account.html', methods = ['POST', 'GET'])
def account_handling():
    email   = session['email']
    user_id = session['user_id']

    dbcursor = conn.cursor(dictionary=True)
    dbcursor.execute("""
        SELECT 
            b.bookingID, 
            b.userID,
            b.routeID, 
            b.seats, 
            b.class,
            b.ticket_date, 
            b.statusID,
            s.status
        FROM bookings b
        JOIN statuses s ON s.statusID = b.statusID
        WHERE b.userID = %s
        AND b.statusID = 2 
        ORDER BY ticket_date DESC
    """, (user_id,))
    booking_history = dbcursor.fetchall() 


    for booking in booking_history:
        dbcursor.execute("""
          SELECT departure_city, departure_time, arrival_city, arrival_time
          FROM routes
          WHERE routeID = %s
        """, (booking['routeID'],))
        rout = dbcursor.fetchone()
        # merge into the booking dict
        booking['departure_city'] = rout['departure_city']
        booking['departure_time'] = rout['departure_time']
        booking['arrival_city']   = rout['arrival_city']
        booking['arrival_time']   = rout['arrival_time']

    return render_template('account.html',
                           bookings=booking_history,
                           email=email)

def calculate_customer_scores(costumer_purchases):
    customer_scores = {}

    for purchase in costumer_purchases:
        user_id = purchase["userID"]         # userID
        seats = purchase["seats"]            # number of seats
        seat_class = purchase["class"]       # seat class
        user_email = purchase["email"]       # email
        price: int = int(purchase["price"])  # price
        ticket_date = purchase["ticket_date"]
        days_until = (ticket_date - date.today()).days
        total_paid: int = calc_final_price(int(price), seats, seat_class, days_until)

        if user_id not in customer_scores:
            customer_scores[user_id] = {
                "userID": user_id,
                "email": user_email,
                "total_seats": 0,
                "total_spent": 0
            }

        customer_scores[user_id]["total_spent"]  += total_paid
        customer_scores[user_id]["total_seats"] += seats

    top_customers = sorted(
        customer_scores.values(),
        key=lambda c : c["total_spent"],
        reverse=True
    )

    return top_customers

def calculate_route_scores(route_purchases):
    route_scores = {}

    for purchase in route_purchases:
        route_id = purchase["routeID"]       # routeID
        seats = purchase["seats"]            # number of seats
        seat_class = purchase["class"]       # seat class
        price: int = int(purchase["price"])  # price
        ticket_date = purchase["ticket_date"]
        days_until = (ticket_date - date.today()).days
        total_paid: int = calc_final_price(int(price), seats, seat_class, days_until)
        departure_city = purchase["departure_city"]
        arrival_city = purchase["arrival_city"]

        if route_id not in route_scores:
            route_scores[route_id] = {
                "routeID": route_id,
                "total_seats": 0,
                "departure_city": departure_city,
                "arrival_city": arrival_city,
                "total_spent": 0
            }

        route_scores[route_id]["total_spent"] += total_paid
        route_scores[route_id]["total_seats"] += seats

    top_routes = sorted(
        route_scores.values(),
        key=lambda c : c["total_spent"],
        reverse=True
    )

    return top_routes


@app.route('/admin', methods = ['POST', 'GET'])
@app.route('/admin.html', methods = ['POST', 'GET'])
@login_required
def admin():

    email   = session['email']
    # admin_user_id = session['user_id']

    dbcursor = conn.cursor(dictionary=True)

    dbcursor.execute("""
        SELECT userID, name, email, usertype
        FROM   users
    """)
    users = dbcursor.fetchall()

    dbcursor.execute("""
        SELECT
            b.bookingID, b.userID,
            u.email         AS user_email,
            r.routeID, r.departure_city, r.arrival_city, r.departure_time, r.arrival_time,
            b.ticket_date, b.seats, b.class, b.statusID, s.status, b.total_paid
        FROM bookings b
        JOIN routes   r ON r.routeID = b.routeID
        JOIN users    u ON u.userID  = b.userID
        JOIN statuses s ON s.statusID = b.statusID
        ORDER BY b.ticket_date
    """)
    all_bookings = dbcursor.fetchall()

    dbcursor.execute("""
        SELECT r.routeID, r.departure_city, r.departure_time, r.arrival_city, r.arrival_time, r.fareID, f.price
        FROM routes r
        JOIN fares  f ON r.fareID = f.fareID
        ORDER BY r.routeID
    """)
    all_routes = dbcursor.fetchall()

    SELECT_statement = """SELECT b.bookingID, b.routeID, b.seats, b.class, b.ticket_date, r.departure_city, r.arrival_city
                          FROM bookings b
                          JOIN routes   r ON b.routeID = r.routeID
                          WHERE ticket_date BETWEEN DATE_SUB( NOW(), INTERVAL 1 MONTH) AND NOW();"""           
    dbcursor.execute(SELECT_statement)   
    last_month_bookings = dbcursor.fetchall()

    SELECT_statement = """SELECT b.bookingID, b.userID, b.ticket_date, b.seats, b.class, u.email, r.fareID, f.price
                          FROM bookings b
                          JOIN users    u ON u.userID = b.userID
                          JOIN routes   r ON r.routeID = b.routeID
                          JOIN fares    f ON f.fareID = r.fareID"""  
    dbcursor.execute(SELECT_statement)   
    costumer_purchases = dbcursor.fetchall()
    customer_scores = calculate_customer_scores(costumer_purchases)

    SELECT_statement = """SELECT b.bookingID, b.routeID, b.ticket_date, b.seats, b.class, r.departure_city, r.arrival_city, r.fareID, f.price
                          FROM bookings b
                          JOIN routes   r ON r.routeID = b.routeID
                          JOIN fares    f ON f.fareID = r.fareID"""  
    dbcursor.execute(SELECT_statement)   
    route_purchases = dbcursor.fetchall()
    route_scores = calculate_route_scores(route_purchases)

    return render_template('admin.html',
                            users=users,
                            bookings=all_bookings,
                            routes=all_routes,
                            email=email,
                            last_month_bookings=last_month_bookings,
                            customer_scores=customer_scores, 
                            route_scores=route_scores
                            )


@app.route('/cancel-booking/<int:user_id>/<int:booking_id>/<int:route_id>', methods = ['POST', 'GET'])
def cancel_booking(user_id, booking_id, route_id):
    uid = session['user_id']

    dbcursor = conn.cursor(buffered=True, dictionary=True)

    dbcursor.execute("""
        SELECT routeID, ticket_date, seats, class, total_paid
        FROM bookings
        WHERE bookingID = %s AND userID = %s
    """, (booking_id, user_id))
    b = dbcursor.fetchone()
    if not b:
        flash("Booking not found.", "warning")
        return redirect(url_for('account_handling'))
    ticket_date = b['ticket_date']
    seat_class = b['class']
    number_of_seats = b['seats']
    total_paid = b['total_paid']

    today = date.today()
    # travel_date = datetime.strptime(ticket_date, "%Y-%m-%d").date()
    days_until  = (ticket_date - today).days

    if days_until <= 30:
        total_paid = total_paid        # 100% of the price will be kept, no refund
        status = 'Refund denied'
    elif days_until > 30 and days_until <= 60:
        total_paid = total_paid * 0.60 # 40% of money kept
        status = 'Partially refunded'
    elif days_until > 60:
        total_paid = 0
        status = 'Fully refunded'

    dbcursor.execute("""
        SELECT statusID, status
        FROM statuses
    """)
    statuses = dbcursor.fetchall()

    for s in statuses:
        if s["status"] == status:
            status_id = s["statusID"]

    UPDATE_statement = """
        UPDATE bookings
        SET total_paid = %s, statusID = %s
        WHERE bookingID = %s AND userID = %s"""
    data = (total_paid, status_id, booking_id, user_id)
    dbcursor.execute(UPDATE_statement, data)

    dbcursor.execute("""
    SELECT business_onboard, standard_onboard FROM route_capacity 
    WHERE routeID = %s AND ticket_date = %s""", (route_id, ticket_date,))
    onboard = dbcursor.fetchone()  
    business_onboard  = int(onboard['business_onboard'])
    standard_onboard  = int(onboard['standard_onboard'])

    if seat_class == 'Business':
        business_onboard -= number_of_seats
    elif seat_class == 'Standard':
        standard_onboard -= number_of_seats

    UPDATE_statement = """
    UPDATE route_capacity
        SET business_onboard  = %s,
            standard_onboard  = %s
    WHERE routeID     = %s
        AND ticket_date = %s
    """
    data = (business_onboard, standard_onboard, route_id, ticket_date)
    dbcursor.execute(UPDATE_statement, data)
    conn.commit()

    if uid != user_id: # admin
        return redirect(url_for('admin'))
    return redirect(url_for('account_handling'))


@app.route('/delete-route/<int:route_id>', methods = ['POST', 'GET'])
def delete_routes(route_id):
    if request.method == 'GET':
        if conn != None:
            if conn.is_connected():                    
                dbcursor = conn.cursor()
                SELECT_statement = "SELECT bookingID, statusID FROM bookings WHERE routeID = %s;"
                dbcursor.execute(SELECT_statement, (route_id,))   
                booking = dbcursor.fetchall()

                counter = 0
                for bookings in booking:
                    status_id = bookings[1]

                    if int(status_id) == 2:
                        counter += 1
                        flash('Cannot delete routes with active bookings')
                        return redirect(url_for('admin'))

                if counter == 0:
                    dbcursor.execute("UPDATE bookings SET routeID = NULL WHERE routeID = %s", (route_id,))

                    delete_statement = f"DELETE FROM routes WHERE routeID = %s"
                    dbcursor.execute(delete_statement, (route_id,))

                    delete_statement = f"DELETE FROM route_capacity WHERE routeID = %s"
                    dbcursor.execute(delete_statement, (route_id,))

                    conn.commit()
                    return redirect(url_for('admin'))
            else:
                print('DB connection error')
        else:
            return('error')
    return redirect(url_for('admin'))


@app.route('/add-route', methods = ['POST', 'GET'])
@app.route('/add-route.html', methods = ['POST', 'GET'])
def add_route():
    if request.method == 'POST':
        new_departure_city: str = request.form['departure-city']
        new_departure_time: str = request.form['departure-time']
        new_arrival_city: str = request.form['arrival-city']
        new_arrival_time: str = request.form['arrival-time']
        new_price: str = request.form['price']
        if conn != None:
            if conn.is_connected():
                dbcursor = conn.cursor()

                SELECT_statement = "SELECT price FROM fares"
                dbcursor.execute(SELECT_statement)
                fares = dbcursor.fetchall()

                for f in fares:
                    if new_price == f:
                        new_fare = new_price//10 - 7

                        INSERT_statement = """ INSERT INTO routes (departure_city, departure_time, arrival_city, arrival_time, fareID) VALUES (%s, %s, %s, %s, %s)"""
                        data = (new_departure_city, new_departure_time, new_arrival_city, new_arrival_time, new_fare)
                        dbcursor.execute(INSERT_statement, data)
                        conn.commit()
                        break

                    else: 
                        INSERT_statement = """ INSERT INTO fares (price) VALUES (%s)"""
                        data = (new_price,)
                        dbcursor.execute(INSERT_statement, data)
                        conn.commit()

                        SELECT_statement = "SELECT fareID FROM fares"
                        dbcursor.execute(SELECT_statement)
                        fare = dbcursor.fetchall()
                        new_fare_id = fare[-1]                  

                        INSERT_statement = """ INSERT INTO routes (departure_city, departure_time, arrival_city, arrival_time, fareID) VALUES (%s, %s, %s, %s, %s)"""
                        data = (new_departure_city, new_departure_time, new_arrival_city, new_arrival_time, new_fare_id[0])
                        dbcursor.execute(INSERT_statement, data)
                        conn.commit()
                        break
                
                flash('New route successfully added.')
                return redirect(url_for('admin'))

    return render_template('add-route.html')


@app.route('/login-to-user/<string:email>/<string:name>', methods = ['POST', 'GET'])
# @admin_required
def login_to_user(email, name):

    session['email'] = email

    dbcursor = conn.cursor()
    SELECT_statement = 'SELECT name, userID FROM users where email = %s;'              
    dbcursor.execute(SELECT_statement, (email,))   
    names = dbcursor.fetchone()
    name = names[0]
    user_id = names[1]

    session['user_id'] = user_id

    session['admin'] = False
    session['role'] = 'Standard'
    session['name'] = name

    return redirect(url_for('home')) 


# login page
@app.route('/login', methods = ['POST', 'GET'])
@app.route('/login.html', methods = ['POST', 'GET'])
def login():
    TABLE_NAME = 'users'
    if request.method == 'POST':
        session['email'] = request.form['email']
        SELECT_statement = 'SELECT userID, email, password, name, usertype FROM ' + TABLE_NAME +';' 
        if conn != None:    #Checking if connection is None
            if conn.is_connected(): #Checking if connection is established                        
                dbcursor = conn.cursor()    #Creating cursor object                
                dbcursor.execute(SELECT_statement)   
                row = dbcursor.fetchall()
                for rows in row:
                    user_id = rows[0]
                    session['user_id'] = user_id
                    email: str = rows[1]
                    pwd: str = rows[2]
                    name: str = rows[3]
                    user_type: str = rows[4]
                    session['name'] = name
                    
                    if user_type == 'Admin':
                        session['role'] = 'admin'
                        admin = True
                    elif user_type == 'Standard':
                        session['role'] = 'standard'
                        admin = False

                    session['admin'] = admin

                    entered_pwd = request.form['password']

                    if request.form['email'] == email and sha256_crypt.verify(str(entered_pwd), pwd):
                        return render_template('home.html', name=session['name'], user=session['email'], admin=admin)
                else:
                    flash('Password or username was wrong, please try again')                  
            else:
                print('DB connection error')
        else:
            print('DBFunc error')

    return render_template('login.html')


# signup page
@app.route('/signup', methods = ['POST', 'GET'])
@app.route('/signup.html', methods = ['POST', 'GET'])
def signup():
    TABLE_NAME = 'users'
    if request.method == 'POST':
        name: str = request.form['name']
        surname: str = request.form['surname']
        nationality: str = request.form['nationality']
        mobile: str = request.form['mobile']
        email: str = request.form['email']

        password: str = request.form['password']
        cpassword: str = request.form['confirm-password']
        hashed = sha256_crypt.hash(str(password))

        usertype: str = 'Standard'
        session['email'] = request.form['email']
        session['name'] = request.form['name']

        if password == cpassword:
            if conn != None:
                if conn.is_connected():
                    dbcursor = conn.cursor()
                    INSERT_statement = """ INSERT INTO users (name, surname, nationality, mobile, email, password, usertype) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                    data = (name, surname, nationality, mobile, email, hashed, usertype)
                    dbcursor.execute(INSERT_statement, data)
                    conn.commit()
                    print('INSERT query executed successfully.')

                    return render_template('home.html', name=session['name'], user=session['email'], admin=False)
                else:
                    print('Database connection error')

        else: 
            flash('Passwords do not match, try again')

    return render_template('signup.html')

@app.route('/about')
@app.route('/about.html')
def about():
    return render_template('about.html')

@app.route('/deals')
@app.route('/deals.html')
def deals():
    return render_template('deals.html')


# user logout button
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# verifies old password, used in password change
@app.route('/verify-old-password', methods=['POST'])
def verify_old_password():
    old_password = request.form['old-password']
    
    user_email = session.get('email')
    
    if not user_email:
        return jsonify({'status': 'failure', 'message': 'User not logged in.'})
    
    TABLE_NAME = 'users'
    SELECT_statement = f"SELECT password FROM users WHERE email = %s"
    
    if conn.is_connected():
        dbcursor = conn.cursor()
        dbcursor.execute(SELECT_statement, (user_email,))
        result = dbcursor.fetchone()
        
        if result and (sha256_crypt.verify(str(old_password), result[0])):  # Assuming passwords are hashed
            return jsonify({'status': 'success', 'message': 'Password verified'})
        else:
            return jsonify({'status': 'failure', 'message': 'Incorrect password'})
    else:
        return jsonify({'status': 'failure', 'message': 'Database connection error'})


# updates password after verifying the password
@app.route('/update-password', methods=['POST'])
def update_password():
    new_password = request.form['new-password']
    new_pwd_hashed = sha256_crypt.hash(str(new_password))
    user_email = session.get('email')
    
    if not user_email:
        return jsonify({'status': 'failure', 'message': 'User not logged in.'})
    
    TABLE_NAME = 'users'
    UPDATE_statement = f"UPDATE {TABLE_NAME} SET password = %s WHERE email = %s"
    
    if conn.is_connected():
        dbcursor = conn.cursor()
        dbcursor.execute(UPDATE_statement, (new_pwd_hashed, user_email))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Password updated successfully'})
    else:
        return jsonify({'status': 'failure', 'message': 'Database connection error'})


# delete account, used in user account management page
@app.route('/delete-account', methods=['POST', 'GET'])
def delete_account():
    email = session.get("email")
    if not email:
        flash('Cannot complete action, try again later')
        return redirect(url_for('account'))
    
    if request.method == 'GET':
        if conn != None:
            if conn.is_connected():                    
                dbcursor = conn.cursor()
                SELECT_statement = "SELECT userID FROM users WHERE email = %s;"
                dbcursor.execute(SELECT_statement, (session.get('email'),))
                uid = dbcursor.fetchone()
                user_id = uid[0]
                
                SELECT_statement = "SELECT bookingID, statusID FROM bookings WHERE userID = %s;"
                dbcursor.execute(SELECT_statement, (user_id,))   
                booking = dbcursor.fetchall()

                counter = 0
                for bookings in booking:

                    status_id = bookings[1]

                    if int(status_id) == 2:
                        counter += 1
                        flash('Cannot delete accounts with an active booking, please try again later or contact our support')
                        return redirect(url_for('account_handling'))
                    
                # if counter >= 1:
                #     flash('Cannot delete accounts with an active booking, please try again later or contact our support')
                #     return redirect(url_for('account_handling'))
                if counter == 0:
                    dbcursor.execute("UPDATE bookings SET userID = NULL WHERE userID = %s", (user_id,))

                    dbcursor.execute("DELETE FROM users WHERE userID = %s", (user_id,))
                    conn.commit() 
                    session.clear()
                    flash('Account was successfully deleted.')
                    return redirect(url_for('home'))
                    
                return redirect(url_for('account_handling'))
            else:
                print('DB connection error')
        else:
            print('DBFunc error')

    return redirect(url_for('account_handling'))


# delete users account from admin side 
@app.route('/delete-user/<int:user_id>', methods = ['POST', 'GET'])
def delete_user(user_id):

    if request.method == 'GET':
        if conn != None:
            if conn.is_connected():
                dbcursor = conn.cursor()
                SELECT_statement = "SELECT bookingID, statusID FROM bookings WHERE userID = %s;"
                dbcursor.execute(SELECT_statement, (user_id,))   
                booking = dbcursor.fetchall()

                SELECT_statement = "SELECT usertype FROM users WHERE userID = %s;"
                dbcursor.execute(SELECT_statement, (user_id,))   
                usertypes = dbcursor.fetchone()
                usertype = usertypes[0]

                if str(usertype) == 'Admin':
                    flash('Cannot delete admin account')
                    return redirect(url_for('admin'))
                
                else:

                    counter = 0
                    for bookings in booking:
                        status_id = bookings[1]

                        if str(usertype) == 'Admin':
                            flash('Cannot delete admin account')
                            return redirect(url_for('admin'))

                        if int(status_id) == 2:
                            counter += 1
                            flash('Cannot delete account for users that have active bookings')
                            return redirect(url_for('admin'))

                    if counter == len(booking):
                        flash('Cannot delete account for users that have active bookings')
                        return redirect(url_for('admin'))
                    else:
                        dbcursor.execute("UPDATE bookings SET userID = NULL WHERE userID = %s", (user_id,))

                        dbcursor.execute("DELETE FROM users WHERE userID = %s", (user_id,))
                        conn.commit()
                            
                        return redirect(url_for('admin'))
        
                return redirect(url_for('admin'))
            else:
                print('DB connection error')
        else:
            print('DBFunc error')

    return redirect(url_for('admin'))
            

@app.route('/book-form')
def book_form():
    return render_template('book-form.html')

def calc_final_price(price, number_of_seats, seat_type, days_until):
 
    price *= int(number_of_seats)  # change price based on the number of seats
    if seat_type == 'Business':    # change price based on seat type
        price *= 2
    # change prices according to discount system
    if days_until >= 80 and days_until <= 90:
        price *= 0.75 # 25% off
    elif days_until >= 60 and days_until <= 79:
        price *= 0.85 # 15% off
    elif days_until >= 45 and days_until <= 59:
        price *= 0.90 # 10% off

    return price


@app.route('/get-price-to-pay', methods = ['POST', 'GET'])
def get_price_to_pay():
    if request.method == 'POST':

        departure_city: str = request.form['leave-city-options']
        arrival_city: str = request.form['arrive-city-options']
        dbcursor = conn.cursor(buffered=True)


        dbcursor.execute("""
        SELECT routeID, fareID, departure_time, arrival_time FROM routes 
        WHERE departure_city = %s AND arrival_city = %s""", (departure_city, arrival_city,))
        routes = dbcursor.fetchone()  # Fetch the travel option details

        if routes is None:
            print("Route ID not found!")
            return "Route ID not found", 404  # Error: Travel option not found

        fare_id = routes[1]

        # get price for route and calculate actual price (with discounts etc)
        dbcursor.execute("""
        SELECT price FROM fares 
        WHERE fareID = %s""", (fare_id,))
        prices = dbcursor.fetchone()

        if prices is None:
            print("Price not found!")
            return "Price option not found", 404
        
        price : int = int(prices[0]) 
        
        data = request.get_json(silent=True) or request.form

        try:
            travel_date = datetime.strptime(data['travel-date'], '%Y-%m-%d').date()
            seats       = int(data['number-of-seats'])
            seat_type   = data['seat-type']
        except (KeyError, ValueError):
            abort(400, 'Missing or invalid fields')

        days_until = (travel_date - date.today()).days
        price      = calc_final_price(price, seats, seat_type, days_until)

        discount_percentage = 0
        if days_until >= 80 and days_until <= 90:
            discount_percentage = 25   # 25% off
        elif days_until >= 60 and days_until <= 79:
            discount_percentage = 15   # 15% off
        elif days_until >= 45 and days_until <= 59:
            discount_percentage = 10   # 10% off

    return jsonify(price=price, discount=discount_percentage)
    

# used by user to book flights, login is required for this page
@app.route('/book', methods = ['POST', 'GET'])
@app.route('/book.html',methods = ['POST', 'GET'])
@login_required
def book():
    business_capacity = int(PLANE_CAPACITY * 0.20)          # 26
    standard_capacity = PLANE_CAPACITY - business_capacity  # 104

    TABLE_NAME = 'bookings'
    if request.method == 'POST':

        departure_city: str = request.form['leave-city-options']
        arrival_city: str = request.form['arrive-city-options']
        entered_date: str = request.form['travel-date']
        # travel_date = datetime.strptime(entered_date, '%Y-%m-%d').date()
        number_of_seats: int = request.form['number-of-seats']
        seat_type: str = request.form['seat-type']
        email : str = session.get('email')

        travel_date = datetime.strptime(entered_date, "%Y-%m-%d").date()
        today       = date.today()
        days_until  = (travel_date - today).days


        if conn != None:
            if conn.is_connected():
                dbcursor = conn.cursor(buffered=True)

                dbcursor.execute("SELECT userID FROM users WHERE email = %s", (email,))
                user = dbcursor.fetchone()  # Assuming email is unique
                if user is None:
                    print("User ID not found!")
                    return "User ID not found", 404  # Error: User not found
                
                user_id = user[0]  # Get the travel_id
                session['user_id'] = user_id

                dbcursor.execute("""
                SELECT routeID, fareID, departure_time, arrival_time FROM routes 
                WHERE departure_city = %s AND arrival_city = %s""", (departure_city, arrival_city,))
                routes = dbcursor.fetchone()  # Fetch the travel option details

                if routes is None:
                    print("Route ID not found!")
                    return "Route ID not found", 404  # Error: Travel option not found

                route_id = routes[0]  # Get the travel_id
                fare_id = routes[1]
                departure_time = routes[2]
                arrival_time = routes[3]

                # get price for route and calculate actual price (with discounts etc)
                dbcursor.execute("""
                SELECT price FROM fares 
                WHERE fareID = %s""", (fare_id,))
                prices = dbcursor.fetchone()

                if prices is None:
                    print("Price not found!")
                    return "Price option not found", 404  
                
                # gets amount of people onboard
                dbcursor.execute("""
                SELECT business_onboard, standard_onboard FROM route_capacity 
                WHERE routeID = %s AND ticket_date = %s""", (route_id, entered_date,))
                onboard = dbcursor.fetchone()  # Fetch the travel option details

                if onboard is None:
                    business_onboard = 0
                    standard_onboard = 0
                else: 
                    business_onboard = int(onboard[0])
                    standard_onboard = int(onboard[1])

                if (seat_type == 'Business' and (int(number_of_seats) + business_onboard) <= business_capacity) or (seat_type == 'Standard' and (int(number_of_seats) + standard_onboard) <= standard_capacity):
                
                    price : int = int(prices[0]) 
                    total_paid = calc_final_price(price, number_of_seats, seat_type, days_until)

                    if seat_type == 'Business':
                        business_onboard += int(number_of_seats)
                    elif seat_type == 'Standard':
                        standard_onboard += int(number_of_seats)

                    if onboard is None: 
                        INSERT_statement = """ INSERT INTO route_capacity (routeID, ticket_date, business_onboard, standard_onboard) VALUES (%s, %s, %s, %s)"""
                        data = (route_id, entered_date, business_onboard, standard_onboard)
                        dbcursor.execute(INSERT_statement, data)
                    else:
                        UPDATE_statement = """
                        UPDATE route_capacity
                            SET business_onboard = %s,
                                standard_onboard = %s
                        WHERE routeID = %s AND ticket_date = %s
                        """
                        # UPDATE_statement = """UPDATE route_capacity SET business_onboard = %s AND standard_onboard = %s WHERE routeID = %s AND ticket_date = %s"""
                        data = (business_onboard, standard_onboard, route_id, entered_date)
                        dbcursor.execute(UPDATE_statement, data)
                        

                    INSERT_statement = """ INSERT INTO bookings (userID, routeID, seats, class, ticket_date, statusID, total_paid) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                    data = (user_id, route_id, number_of_seats, seat_type, entered_date, 2, total_paid)
                    dbcursor.execute(INSERT_statement, data)
                    conn.commit()


                    return render_template('receipt.html', email=email, user_id=user_id, 
                                        departure_city=departure_city, arrival_city=arrival_city, route_id=route_id, 
                                        date=entered_date, departure_time=departure_time, arrival_time=arrival_time, 
                                        number_of_seats=number_of_seats, seat_type=seat_type, price=total_paid
                                        )
                else:
                    flash('Not enough capacity', 'error')
                    return redirect(url_for('book'))
            else:
                print('Database connection error')
    email = session.get('email')
    role = session.get('role')
    return render_template('book.html', user=email, role=role)

# receipt page
@app.route('/receipt', methods = ['POST', 'GET']) 
@app.route('/receipt.html', methods = ['POST', 'GET'])
def receipt():
    if request.method == 'POST':
        email = session.get('email')
        user_id = session.get('user_id')
        route_id = session.get('route_id')
        if conn != None:
            if conn.is_connected():
                dbcursor = conn.cursor()

                dbcursor.execute("""
                SELECT departure_city, departure_time, arrival_city, arrival_time FROM routes 
                WHERE routeID = %s""", (route_id,))
                travel = dbcursor.fetchall()  # Fetch the travel option details
                if travel is None:
                    print("Route not found!")
                    return "Route not found", 404  # Error: User not found

    return render_template('receipt.html')


@app.post("/accept_cookies")
def accept_cookies():
    resp = make_response("ok")
    resp.set_cookie("cookie_consent", "accepted",
                    max_age=60*60*24*365, samesite="Lax")
    return resp

@app.post("/decline_cookies")
def decline_cookies():
    resp = make_response("ok")
    resp.set_cookie("cookie_consent", "declined",
                    max_age=60*60*24*365, samesite="Lax")
    return resp


@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404


@app.errorhandler(401)
def un_authorised(error):
    return render_template('401.html'), 401


# if __name__ == '__main__':
#     for i in range (13000, 18000):
#         try:
#             app.run(debug=True)
#             break
#         except OSError as e:
#             print("Port {i} not available".format(i))
if __name__ == '__main__':
    # check_booking_validity()
    print('Run command implemented successfully.')
    app.run(debug=True)