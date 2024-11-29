from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
CORS(app)

DB_HOST = 'dpg-ct2naf3tq21c73b4s8lg-a.singapore-postgres.render.com'
DB_PORT = '5432'
DB_NAME = 'facetwahdb'
DB_USER = 'facetwahdb_user'
DB_PASS = 'FDmm3mM50lE91i0WFlXr4VFtyKRexoFi'

API_KEYS = [
   "U6sZ7EsPyJAcaOAgSVpT4mAZeNKOJOc7",  # Key 1
   "npApDeN2gsnk6syw2ZzpZWwQQcQPf0UK",  # Key 2
   "Eqs4PNncfylUPXnnoJjtbOIfrJ6WpGbm",  # Key 3
   "MbxvQucScbE349dVxRlvaLUrILCNhPfh",  # Key 4
   "GJi5TgrZzqSkstbYebhmMF9BGsh59oQm"   # Key 5
]

ph = PasswordHasher()

def get_db_connection():
   connection = psycopg2.connect(
       host=DB_HOST,
       port=DB_PORT,
       dbname=DB_NAME,
       user=DB_USER,
       password=DB_PASS
   )
   return connection

def check_api_key():
   auth_header = request.headers.get('Authorization')
   if not auth_header:
       return False
  
   token = auth_header.split(" ")[1] if " " in auth_header else ""
  
   if token in API_KEYS:
       return True
   return False

@app.route('/login', methods=['POST'])
def login():
   if not check_api_key():
       return jsonify({"status": "error", "message": "Invalid API Key"}), 403

   data = request.json
   username = data.get('username')
   password = data.get('password')

   if not username or not password:
       return jsonify({'status': 'error', 'message': 'Username and password are required'}), 400

   connection = get_db_connection()
   cursor = connection.cursor()

   try:
       # Query to fetch password and position
       cursor.execute('SELECT pass, position FROM creds WHERE username = %s', (username,))
       result = cursor.fetchone()

       if not result:
           return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

       hashed_password = result[0]
       position = result[1]  # Fetch position from the database

       # Verify the provided password against the stored hash
       try:
           ph.verify(hashed_password, password)
           return jsonify({
               'status': 'success',
               'message': 'Login successful',
               'user': username,
               'position': position  # Include the position in the response
           }), 200
       except VerifyMismatchError:
           return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401
   finally:
       cursor.close()
       connection.close()


@app.route('/register', methods=['POST'])
def register():
   if not check_api_key():
       return jsonify({"status": "error", "message": "Invalid API Key"}), 403


   data = request.json
   name = data.get('name')
   age = data.get('age')
   department = data.get('department')
   position = data.get('position')
   address = data.get('address')
   employee_id = data.get('employee_id')


   # Field validations
   if not name or not age or not department or not position or not address or not employee_id:
       return jsonify({'status': 'error', 'message': 'All fields are required'}), 400


   try:
       age = int(age)
       employee_id = int(employee_id)
   except ValueError:
       return jsonify({'status': 'error', 'message': 'Age and Employee ID must be integers'}), 400


   valid_departments = ['BRM and Creative Media','Project Management Unit','Quality Assurance','Technical Support','Development']
   if department.strip().upper() not in [dept.upper() for dept in valid_departments]:
    return jsonify({'status': 'error', 'message': 'Invalid department'}), 400



   connection = get_db_connection()
   cursor = connection.cursor()


   try:
       cursor.execute(
           '''
           INSERT INTO employee (name, age, department, position, address, employee_id)
           VALUES (%s, %s, %s, %s, %s, %s)
           ''',
           (name, age, department, position, address, employee_id)
       )
       connection.commit()
       return jsonify({'status': 'success', 'message': 'Employee registered successfully'}), 200
   except psycopg2.IntegrityError:
       return jsonify({'status': 'error', 'message': 'Employee ID already exists'}), 400
   finally:
       cursor.close()
       connection.close()

@app.route('/employees', methods=['GET'])
def get_employees():
    """
    Fetch all rows from the employee table.
    """
    if not check_api_key():
        return jsonify({"status": "error", "message": "Invalid API Key"}), 403

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Query to fetch all employees
        cursor.execute('SELECT id, name, age, department, position, address, employee_id FROM employee')
        rows = cursor.fetchall()

        # Convert rows into a list of dictionaries
        employees = [
            {
                'id': row[0],
                'name': row[1],
                'age': row[2],
                'department': row[3],
                'position': row[4],
                'address': row[5],
                'employee_id': row[6]
            }
            for row in rows
        ]

        return jsonify({'status': 'success', 'employees': employees}), 200
    finally:
        cursor.close()
        connection.close()


@app.route('/employee/<int:id>', methods=['GET'])
def get_employee_by_id(id):
    """
    Fetch a single employee by ID.
    """
    if not check_api_key():
        return jsonify({"status": "error", "message": "Invalid API Key"}), 403

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Query to fetch the employee by ID
        cursor.execute('SELECT id, name, age, department, position, address, employee_id FROM employee WHERE id = %s', (id,))
        row = cursor.fetchone()

        if not row:
            return jsonify({'status': 'error', 'message': 'Employee not found'}), 404

        # Convert the row into a dictionary
        employee = {
            'id': row[0],
            'name': row[1],
            'age': row[2],
            'department': row[3],
            'position': row[4],
            'address': row[5],
            'employee_id': row[6]
        }

        return jsonify({'status': 'success', 'employee': employee}), 200
    finally:
        cursor.close()
        connection.close()

if __name__ == '__main__':
   app.run(debug=True, host='0.0.0.0', port=5000)
