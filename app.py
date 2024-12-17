from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime  
import subprocess
import os
import signal
import numpy as np
import io

app = Flask(__name__)
CORS(app)


# Database configuration
DB_HOST = 'dpg-ct2naf3tq21c73b4s8lg-a.singapore-postgres.render.com'
DB_PORT = '5432'
DB_NAME = 'facetwahdb'
DB_USER = 'facetwahdb_user'
DB_PASS = 'FDmm3mM50lE91i0WFlXr4VFtyKRexoFi'


# API Keys
API_KEYS = [
    "U6sZ7EsPyJAcaOAgSVpT4mAZeNKOJOc7",
    "npApDeN2gsnk6syw2ZzpZWwQQcQPf0UK",
    "Eqs4PNncfylUPXnnoJjtbOIfrJ6WpGbm",
    "MbxvQucScbE349dVxRlvaLUrILCNhPfh",
    "GJi5TgrZzqSkstbYebhmMF9BGsh59oQm"
]


# Password hasher
ph = PasswordHasher()
current_processes = []


# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


# API Key validation function
def check_api_key():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False
    token = auth_header.split(" ")[1] if " " in auth_header else ""
    return token in API_KEYS


# Decorator for API key validation
def require_api_key(func):
    def wrapper(*args, **kwargs):
        if not check_api_key():
            return jsonify({'status': 'error', 'message': 'Invalid or missing API key'}), 403
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# Run a Python script
def run_python_script(script_name, args=None):
    try:
        args = args or []
        process = subprocess.Popen(
            ['python3', script_name] + args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        current_processes.append(process)
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            return {'status': 'success', 'output': stdout.decode()}
        return {'status': 'error', 'output': stderr.decode()}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# Script management endpoints
@app.route('/run-script', methods=['POST'])
@require_api_key
def run_script():
    result = run_python_script('main.py')
    return jsonify(result), 200 if result['status'] == 'success' else 400


@app.route('/stop-script', methods=['POST'])
@require_api_key
def stop_script():
    try:
        for process in current_processes:
            os.kill(process.pid, signal.SIGTERM)
        current_processes.clear()
        return jsonify({'status': 'success', 'message': 'All scripts terminated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Login endpoint
@app.route('/login', methods=['POST'])
@require_api_key
def login():
    data = request.json
    username, password = data.get('username'), data.get('password')
    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username and password are required'}), 400


    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT pass, position FROM creds WHERE username = %s', (username,))
        result = cursor.fetchone()
        if not result:
            return jsonify({'status': 'error', 'message': 'Invalid username or password!'}), 401


        hashed_password, position = result
        ph.verify(hashed_password, password)
        return jsonify({'status': 'success', 'user': username, 'position': position}), 200
    except VerifyMismatchError:
        return jsonify({'status': 'error', 'message': 'Invalid username or password!'}), 401
    finally:
        cursor.close()
        connection.close()


# Register a face
@app.route('/register', methods=['POST'])
@require_api_key
def register_face():
    data = request.json
    fields = ['name', 'age', 'department', 'position', 'address', 'employee_id']
    if not all(data.get(field) for field in fields):
        return jsonify({'status': 'error', 'message': 'All fields are required'}), 400


    args = [data[field] for field in fields]
    result = run_python_script('reg.py', args)
    return jsonify(result), 200 if result['status'] == 'success' else 400


# Fetch all employees
@app.route('/employees', methods=['GET'])
@require_api_key
def get_employees():
    """Endpoint to fetch all employees."""
    cursor = None  
    connection = None  
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
      
        cursor.execute('SELECT id, name, age, department, position, address, employee_id FROM face_encodings')
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

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        if cursor is not None:
            cursor.close()  
        if connection is not None:
            connection.close()  



#EMPLOYEE DETAILS
@app.route('/employee/<int:id>', methods=['GET'])
@require_api_key
def get_employee_by_id(id):
    """Endpoint to fetch employee data by ID, ensuring LIFO order for returned results."""
    cursor = None
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = '''
        (
        SELECT 
            fe.id, 
            fe.name, 
            fe.age, 
            fe.department, 
            fe.position, 
            fe.address, 
            fe.employee_id, 
            es.status, 
            TO_CHAR(es.status_date, 'YY-MM-DD') AS status_date,  -- Updated date format
            NULL AS in_date, 
            NULL AS in_time, 
            NULL AS out_time, 
            NULL AS remarks
        FROM 
            face_encodings fe
        JOIN 
            public.employee_status es ON fe.id = es.id
        WHERE 
            fe.id = %s
            AND TO_CHAR(es.status_date, 'YYYY-MM-DD') != TO_CHAR(
                (SELECT in_time 
                 FROM public.attendance 
                 WHERE id = fe.id 
                 ORDER BY in_time DESC LIMIT 1), 
                'YYYY-MM-DD'
            )
        ORDER BY 
            es.status_date DESC
        )
        UNION ALL
        (
        SELECT 
            fe.id, 
            fe.name, 
            fe.age, 
            fe.department, 
            fe.position, 
            fe.address, 
            fe.employee_id, 
            NULL AS status, 
            NULL AS status_date,
            TO_CHAR(a.in_time, 'YYYY-MM-DD HH24:MI:SS') AS in_date,  -- Full time format
            TO_CHAR(a.in_time, 'YYYY-MM-DD HH24:MI:SS') AS in_time,  -- Full time format
            TO_CHAR(a.out_time, 'YYYY-MM-DD HH24:MI:SS') AS out_time,  -- Full time format
            a.remarks
        FROM 
            face_encodings fe
        JOIN 
            public.attendance a ON fe.id = a.id
        WHERE 
            fe.id = %s
            AND NOT EXISTS (
                SELECT 1 
                FROM public.employee_status es 
                WHERE es.id = fe.id 
                AND TO_CHAR(es.status_date, 'YYYY-MM-DD') = TO_CHAR(a.in_time, 'YYYY-MM-DD')
            )
        ORDER BY 
            a.in_time DESC
        )
        UNION ALL
        (
        SELECT
            fe.id,
            fe.name,
            fe.age,
            fe.department,
            fe.position,
            fe.address,
            fe.employee_id,
            es.status,
            TO_CHAR(es.status_date, 'YY-MM-DD') AS status_date,  -- Updated date format
            NULL AS in_date,
            NULL AS in_time,
            NULL AS out_time,
            NULL AS remarks
        FROM
            face_encodings fe
        JOIN
            public.employee_status es ON fe.id = es.id
        WHERE
            fe.id = %s
            AND (es.status = 'Absent' OR es.status = 'On Leave')
        ORDER BY 
            es.status_date DESC
        );
        '''

        # Execute the query with the same 'id' passed three times
        cursor.execute(query, (id, id, id))
        rows = cursor.fetchall()

        # Process and return the results
        if rows:
            employees = [
                {
                    'id': row[0],
                    'name': row[1],
                    'age': row[2],
                    'department': row[3],
                    'position': row[4],
                    'address': row[5],
                    'employee_id': row[6],
                    'status': row[7],
                    'status_date': row[8],  # status date with updated format
                    'in_date': row[9],
                    'in_time': row[10],
                    'out_time': row[11],
                    'remarks': row[12]
                }
                for row in rows
            ]
            return jsonify({'status': 'success', 'employees': employees}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Employee not found'}), 404

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

#EMPLOYEE COUNT 
@app.route('/employee_count', methods=['GET'])
@require_api_key
def employee_count():
    """
    Fetch the total count of employees in the database.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Query to count the number of employees
        cursor.execute('SELECT COUNT(*) FROM face_encodings')
        employee_count = cursor.fetchone()[0]  # Get the count from the result

        return jsonify({
            'status': 'success',
            'employee_count': employee_count  # Return the employee count
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()

#ADD LEAVE
@app.route('/attendance/<int:id>/add_leave', methods=['POST'])
@require_api_key
def add_leave_days(id):
    """
    Add or update leave days for a record in the attendance table identified by id.
    """
    data = request.json
    leave_days = data.get('leave_days')

    # Validate the leave_days field
    if leave_days is None or not isinstance(leave_days, int) or leave_days <= 0:
        return jsonify({'status': 'error', 'message': 'Leave days must be a positive integer'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Check if the record exists in the face_encodings table
        cursor.execute('SELECT id FROM public.face_encodings WHERE id = %s', (id,))
        row = cursor.fetchone()

        if row:
            # Add a new leave record in employee_status table
            cursor.execute(
                '''
                INSERT INTO public.employee_status (id, on_leave, days_leave, status, status_date, leave_end_date)
                VALUES (%s, TRUE, %s, 'on_leave', CURRENT_DATE, CURRENT_DATE + INTERVAL '1 day' * %s);
                ''',
                (id, leave_days, leave_days)
            )
            connection.commit()

            return jsonify({
                'status': 'success',
                'message': f'{leave_days} leave days added for record ID {id}.'
            }), 200
        else:
            return jsonify({'status': 'error', 'message': f'Record with ID {id} not found in face_encodings.'}), 404

    except Exception as e:
        connection.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


#MARK ABSENT
@app.route('/mark_absent', methods=['POST'])
@require_api_key
def mark_absent():
    try:
        data = request.get_json()
        person_id = data.get('id')
        absent_date = data.get('date')

        # Validate ID
        if not person_id:
            return jsonify({"error": "id is required"}), 400

        try:
            person_id = int(person_id)
        except ValueError:
            return jsonify({"error": "Invalid id, must be an integer"}), 400

        # Connect to the database
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the person exists
        cursor.execute("SELECT name FROM face_encodings WHERE id = %s", (person_id,))
        person = cursor.fetchone()
        if not person:
            return jsonify({"error": "Person with the specified ID does not exist"}), 404

        # Check if the employee has an in_time recorded for today
        cursor.execute("""
            SELECT 1 
            FROM public.attendance 
            WHERE id = %s AND in_time::date = CURRENT_DATE AND in_time IS NOT NULL
        """, (person_id,))
        attendance_record = cursor.fetchone()
        if attendance_record:
            return jsonify({"error": "Employee already has an in_time recorded for today and cannot be marked as absent."}), 400

        # Insert the absence record
        cursor.execute("""
            INSERT INTO public.employee_status (id, on_leave, days_leave, status, status_date, leave_end_date)
            VALUES (%s, FALSE, 0, 'absent', CURRENT_DATE, NULL)
            ON CONFLICT (id, status_date) DO NOTHING
        """, (person_id,))

        # Commit transaction
        connection.commit()

        return jsonify({"message": f"Person {person_id} marked as absent."}), 200

    except Exception as e:
        # Log error details for debugging
        print(f"Error occurred: {e}")
        return jsonify({"error": str(e)}), 500

    finally:
        # Ensure the connection is closed
        cursor.close()
        connection.close()




#REMOVE EMPLOYEE 
@app.route('/face_encoding/delete/<int:face_encoding_id>', methods=['POST'])
@require_api_key
def delete_face_encoding(face_encoding_id):
    try:
        # Connect to the database
        connection = get_db_connection()
        cursor = connection.cursor()

        # Query to delete the row based on the provided id
        cursor.execute("""
            DELETE FROM public.face_encodings
            WHERE id = %s;
        """, (face_encoding_id,))

        # Commit changes
        connection.commit()

        # Check if any row was deleted
        if cursor.rowcount == 0:
            return jsonify({"message": "Face encoding not found"}), 404

        # Close the connection
        cursor.close()

        # Return success message
        return jsonify({"message": f"Face encoding with id {face_encoding_id} deleted successfully"}), 200

    except Exception as e:
        # Handle errors
        return jsonify({"error": str(e)}), 500





# COUNT ABSENT to do
@app.route('/count_absent', methods=['GET'])
@require_api_key
def count_absent():
    try:
        # Connect to the database
        conn = psycopg2.connect(
            dbname="facetwahdb",
            user="facetwahdb_user",
            password="FDmm3mM50lE91i0WFlXr4VFtyKRexoFi",
            host="dpg-ct2naf3tq21c73b4s8lg-a.singapore-postgres.render.com"
        )
        cursor = conn.cursor()

       
        cursor.execute("""
           SELECT COUNT(*) AS absent_today_count
           FROM public.employee_status
           WHERE status = 'absent' 
           AND status_date = CURRENT_DATE;
        """)
        absent_count = cursor.fetchone()[0]  # Fetch the count from the query result

        # Close the connection
        cursor.close()
        conn.close()

        # Return the count of absent employees
        return jsonify({"absent_count": absent_count}), 200

    except Exception as e:
        # Handle errors
        return jsonify({"error": str(e)}), 500



#LATE COUNT done
@app.route('/attendance/late_count', methods=['GET'])
@require_api_key
def late_count():
    """
    Fetch the count of employees marked as 'late' for a specific date or all records.
    Excludes employees who are on leave.
    Query Parameters:
        - date (optional): Filter results for a specific date (format: YYYY-MM-DD).
    """
    date = request.args.get('date')  # Get the optional 'date' parameter

    try:
        # Connect to the database
        conn = psycopg2.connect(
            dbname="facetwahdb",
            user="facetwahdb_user",
            password="FDmm3mM50lE91i0WFlXr4VFtyKRexoFi",
            host="dpg-ct2naf3tq21c73b4s8lg-a.singapore-postgres.render.com"
        )
        cursor = conn.cursor()

        if date:
            try:
                # Validate the date format
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

            query = """
                SELECT COUNT(*) 
                FROM public.attendance 
                WHERE remarks ILIKE '%late%' 
                  AND DATE(in_time) = %s
                  AND id NOT IN (
                      SELECT id
                      FROM public.employee_status
                      WHERE on_leave = true
                        AND leave_end_date >= CURRENT_DATE
                  );
            """
            cursor.execute(query, (date,))
        else:
            query = """
                SELECT COUNT(*) 
                FROM public.attendance 
                WHERE remarks ILIKE '%late%' 
                  AND CURRENT_DATE = DATE(in_time)
                  AND id NOT IN (
                      SELECT id
                      FROM public.employee_status
                      WHERE on_leave = true
                        AND leave_end_date >= CURRENT_DATE
                  );
            """
            cursor.execute(query)

        result = cursor.fetchone()
        late_employee_count = result[0] if result else 0

        return jsonify({"late_employee_count": late_employee_count}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()



# LEAVE COUNT
@app.route('/employee_status/on_leave', methods=['GET'])
@require_api_key
def get_on_leave_count():
    """
    Get the count of employees who are currently on leave based on the current date.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Query to count employees currently on leave, based on leave_start and leave_end dates
        query = """
            SELECT COUNT(*) AS total_on_leave 
            FROM public.employee_status 
            WHERE on_leave = TRUE 
              AND status_date <= CURRENT_DATE 
              AND (leave_end_date IS NULL OR leave_end_date >= CURRENT_DATE)
        """
        cursor.execute(query)
        row = cursor.fetchone()

        if row:
            on_leave_count = row[0]
            return jsonify({
                'status': 'success',
                'onleave_count': on_leave_count  # The total number of employees on leave
            }), 200
        else:
            return jsonify({'status': 'error', 'message': 'No employees on leave.'}), 404

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()



# PRESENT PER DEPARTMENT
@app.route('/present_by_department', methods=['GET'])
@require_api_key
def get_present_by_department():
   
    query = """
    WITH current_day_metrics AS (
    SELECT 
        fe.department,
        COUNT(fe.id) AS total_employee_count,
        COUNT(es.id) AS on_leave_count,
        COUNT(CASE WHEN att.id IS NOT NULL THEN 1 END) AS present_employee_count
    FROM public.face_encodings fe
    LEFT JOIN public.employee_status es
        ON fe.id = es.id 
        AND es.on_leave = true 
        AND es.leave_end_date >= CURRENT_DATE
    LEFT JOIN public.attendance att
        ON fe.id = att.id 
        AND DATE(att.in_time) = CURRENT_DATE
    GROUP BY fe.department
)
SELECT 
    department,
    total_employee_count,
    on_leave_count,
    present_employee_count
FROM current_day_metrics;
    """
  
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()
      
        # Execute the query to get present employees by department for today
        cursor.execute(query)
        result = cursor.fetchall()
      
        # If no data is found (i.e., no employees present), return an empty list
        if not result:
            return jsonify({"message": "No employees present today"}), 404
      
        # Format the result into JSON and return
        response = []
        for row in result:
            response.append({
                "department": row[0],
                "total_employee_count": row[1],
                "on_leave_count": row[2],
                "present_employee_count": row[3]  # Adding present_employee_count here
            })

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        # Close the connection
        cursor.close()
        conn.close()

#REPORT
@app.route('/attendance/late_report', methods=['GET'])
@require_api_key
def late_count_report():
    """
    Fetch the count of employees marked as 'late' for the current month.
    Excludes employees who are on leave.
    """
    try:
        # Connect to the database
        conn = psycopg2.connect(
            dbname="facetwahdb",
            user="facetwahdb_user",
            password="FDmm3mM50lE91i0WFlXr4VFtyKRexoFi",
            host="dpg-ct2naf3tq21c73b4s8lg-a.singapore-postgres.render.com"
        )
        cursor = conn.cursor()

        # Get the current month and year for the query
        current_month = datetime.now().month
        current_year = datetime.now().year

        query = """
            SELECT a.id, COUNT(a.remarks) AS late_count
            FROM public.attendance a
            WHERE EXTRACT(YEAR FROM a.in_time) = EXTRACT(YEAR FROM CURRENT_DATE)  -- Ensures it is the current year
              AND EXTRACT(MONTH FROM a.in_time) = EXTRACT(MONTH FROM CURRENT_DATE)  -- Ensures it is the current month
              AND a.remarks ILIKE '%late%'  -- Filters for remarks containing the word 'late'
              AND NOT EXISTS (
                  SELECT 1
                  FROM public.employee_status es
                  WHERE es.id = a.id
                  AND es.on_leave = true
                  AND a.in_time BETWEEN es.status_date AND COALESCE(es.leave_end_date, CURRENT_DATE)  -- Handles leave dates
              )
            GROUP BY a.id;
        """
        cursor.execute(query)

        results = cursor.fetchall()
        late_employee_counts = [{"employee_id": row[0], "late_count": row[1]} for row in results]

        return jsonify({"late_employee_counts": late_employee_counts}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

#SUMMARY ATTENDANCE
@app.route('/attendance/<string:period>', methods=['GET'])
@require_api_key
def get_attendance(period):
    """
    Fetch attendance count per department for a specified period (weekly, monthly, annual).
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        if period == 'weekly':
            date_condition = "EXTRACT(week FROM a.in_time) = EXTRACT(week FROM CURRENT_DATE)"
            query = """
            WITH employee_attendance AS (
                SELECT
                    fe.department,
                    fe.id AS employee_id,
                    COUNT(CASE WHEN att.id IS NOT NULL THEN 1 END) AS present_days_count,
                    EXTRACT(DOW FROM CURRENT_DATE) AS current_week_day_count
                FROM public.face_encodings fe
                LEFT JOIN public.attendance att
                    ON fe.id = att.id
                    AND att.in_time >= DATE_TRUNC('week', CURRENT_DATE)
                GROUP BY fe.department, fe.id
            ),
            department_attendance AS (
                SELECT 
                    e.department,
                    SUM((e.present_days_count * 100.0) / e.current_week_day_count) AS total_attendance_percentage,
                    COUNT(e.employee_id) AS department_employee_count
                FROM employee_attendance e
                GROUP BY e.department
            )
            SELECT 
                e.department,
                ROUND(da.total_attendance_percentage / da.department_employee_count, 2) AS department_attendance_percentage
            FROM department_attendance da
            JOIN employee_attendance e
                ON e.department = da.department
            GROUP BY e.department, da.total_attendance_percentage, da.department_employee_count
            ORDER BY e.department;
            """
        
        elif period == 'monthly':
            date_condition = "a.in_time >= NOW() - INTERVAL '1 month'"
            query = """
            WITH employee_attendance AS (
                SELECT
                    fe.department,
                    fe.id AS employee_id,
                    DATE_TRUNC('week', att.in_time) AS week_start,
                    COUNT(CASE WHEN att.id IS NOT NULL THEN 1 END) AS present_days_count,
                    7 AS current_week_day_count -- Assuming a standard week of 7 days
                FROM public.face_encodings fe
                LEFT JOIN public.attendance att
                    ON fe.id = att.id
                    AND att.in_time >= DATE_TRUNC('month', CURRENT_DATE) -- Filter for the current month
                GROUP BY fe.department, fe.id, DATE_TRUNC('week', att.in_time)
            ),
            weekly_department_attendance AS (
                SELECT 
                    e.department,
                    e.week_start,
                    SUM((e.present_days_count * 100.0) / e.current_week_day_count) AS weekly_attendance_percentage,
                    COUNT(e.employee_id) AS department_employee_count
                FROM employee_attendance e
                GROUP BY e.department, e.week_start
            ),
            monthly_department_attendance AS (
                SELECT 
                    wda.department,
                    SUM(wda.weekly_attendance_percentage) / COUNT(wda.week_start) AS monthly_attendance_percentage
                FROM weekly_department_attendance wda
                GROUP BY wda.department
            )
            SELECT 
                mda.department,
                ROUND(mda.monthly_attendance_percentage, 2) AS department_monthly_attendance_percentage
            FROM monthly_department_attendance mda
            ORDER BY mda.department;
            """

        elif period == 'annual':
            date_condition = "a.in_time >= NOW() - INTERVAL '1 year'"
            query = """
            WITH employee_attendance AS (
                SELECT
                    fe.department,
                    fe.id AS employee_id,
                    COUNT(CASE WHEN att.id IS NOT NULL THEN 1 END) AS present_days_count,
                    EXTRACT(DOW FROM CURRENT_DATE) AS current_week_day_count
                FROM public.face_encodings fe
                LEFT JOIN public.attendance att
                    ON fe.id = att.id
                    AND att.in_time >= DATE_TRUNC('year', CURRENT_DATE)
                GROUP BY fe.department, fe.id
            ),
            department_attendance AS (
                SELECT 
                    e.department,
                    SUM((e.present_days_count * 100.0) / e.current_week_day_count) AS total_attendance_percentage,
                    COUNT(e.employee_id) AS department_employee_count
                FROM employee_attendance e
                GROUP BY e.department
            )
            SELECT 
                e.department,
                ROUND(da.total_attendance_percentage / da.department_employee_count, 2) AS department_attendance_percentage
            FROM department_attendance da
            JOIN employee_attendance e
                ON e.department = da.department
            GROUP BY e.department, da.total_attendance_percentage, da.department_employee_count
            ORDER BY e.department;
            """

        else:
            return jsonify({'status': 'error', 'message': 'Invalid period. Use weekly, monthly, or annual.'}), 400

        cursor.execute(query)
        rows = cursor.fetchall()

        # Process the results
        attendance_count_per_department = [
            {
                'department': row[0],
                'attendance_count': round(row[1], 2)  
            }
            for row in rows
        ]

        return jsonify({'status': 'success', 'attendance': attendance_count_per_department}), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        cursor.close()
        connection.close()


#EMPLOYEE GRAPH
@app.route('/employee_summary', methods=['GET'])
@require_api_key
def get_employee_summary():
   department = request.args.get('department')
   timeframe = request.args.get('timeframe', 'weekly')  # Default to weekly if no timeframe is provided


   if not department:
       return jsonify({"error": "Department parameter is required"}), 400


   if timeframe not in ['weekly', 'monthly']:
       return jsonify({"error": "Invalid timeframe parameter. Use 'weekly' or 'monthly'."}), 400


   print(f"Filtering by department: {department} and timeframe: {timeframe}")  # Log the department and timeframe


   # Weekly query
   weekly_query = """
   WITH current_day_metrics AS (
       SELECT
           fe.department,
           COUNT(fe.id) AS total_employee_count,
           COUNT(es.id) AS on_leave_count,
           COUNT(CASE WHEN att.id IS NOT NULL THEN 1 END) AS present_employee_count
       FROM public.face_encodings fe
       LEFT JOIN public.employee_status es
           ON fe.id = es.id
           AND es.on_leave = true
           AND es.leave_end_date >= CURRENT_DATE
       LEFT JOIN public.attendance att
           ON fe.id = att.id
           AND DATE(att.in_time) = CURRENT_DATE
       WHERE fe.department = %s
       GROUP BY fe.department
   ),
   employee_attendance AS (
       SELECT
           fe.department,
           fe.id AS employee_id,
           fe.name AS employee_name,
           COUNT(CASE WHEN att.id IS NOT NULL THEN 1 END) AS present_days_count,
           EXTRACT(DOW FROM CURRENT_DATE) AS current_week_day_count
       FROM public.face_encodings fe
       LEFT JOIN public.attendance att
           ON fe.id = att.id
           AND att.in_time >= DATE_TRUNC('week', CURRENT_DATE)
       WHERE fe.department = %s
       GROUP BY fe.department, fe.id, fe.name
   )
   SELECT
       e.department,
       e.employee_id,
       e.employee_name,
       e.present_days_count,
       e.current_week_day_count,
       ROUND((e.present_days_count * 100.0) / e.current_week_day_count, 2) AS attendance_percentage
   FROM employee_attendance e
   JOIN current_day_metrics cdm
       ON e.department = cdm.department
   ORDER BY e.employee_id;
   """


   # Monthly query
   monthly_query = """
   WITH current_month_metrics AS (
       SELECT
           fe.department,
           COUNT(fe.id) AS total_employee_count,
           COUNT(es.id) AS on_leave_count,
           COUNT(CASE WHEN att.id IS NOT NULL THEN 1 END) AS present_employee_count
       FROM public.face_encodings fe
       LEFT JOIN public.employee_status es
           ON fe.id = es.id
           AND es.on_leave = true
           AND es.leave_end_date >= CURRENT_DATE
       LEFT JOIN public.attendance att
           ON fe.id = att.id
           AND DATE(att.in_time) >= DATE_TRUNC('month', CURRENT_DATE)
           AND DATE(att.in_time) < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 MONTH'
       WHERE fe.department = %s
       GROUP BY fe.department
   ),
   employee_attendance AS (
       SELECT
           fe.department,
           fe.id AS employee_id,
           fe.name AS employee_name,
           COUNT(DISTINCT DATE(att.in_time)) AS present_days_count,
           COUNT(DISTINCT CASE
               WHEN EXTRACT(DOW FROM DATE(att.in_time)) BETWEEN 1 AND 5 -- weekdays (Mon-Fri)
               THEN DATE(att.in_time)
               END) AS total_working_days_count
       FROM public.face_encodings fe
       LEFT JOIN public.attendance att
           ON fe.id = att.id
           AND att.in_time >= DATE_TRUNC('month', CURRENT_DATE)
           AND att.in_time < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 MONTH'
       WHERE fe.department = %s
       GROUP BY fe.department, fe.id, fe.name
   ),
   working_days_in_month AS (
       SELECT
           COUNT(DISTINCT DATE) AS total_working_days
       FROM generate_series(DATE_TRUNC('month', CURRENT_DATE), CURRENT_DATE, '1 day'::interval) AS DATE
       WHERE EXTRACT(DOW FROM DATE) BETWEEN 1 AND 5 -- Monday to Friday
   )
   SELECT
       e.department,
       e.employee_id,
       e.employee_name,
       e.present_days_count,
       w.total_working_days,
       ROUND((e.present_days_count * 100.0) / w.total_working_days, 2) AS attendance_percentage
   FROM employee_attendance e
   JOIN working_days_in_month w ON true
   ORDER BY e.employee_id;
   """


   # Select the correct query based on timeframe
   query = weekly_query if timeframe == 'weekly' else monthly_query


   try:
       # Connect to the database
       conn = get_db_connection()
       cursor = conn.cursor()


       # Log the department, timeframe, and query for debugging
       print(f"Executing {timeframe} query with department: {department}")
       cursor.execute(query, (department, department))  # Pass department twice
       result = cursor.fetchall()


       # If no data is found, return an appropriate message
       if not result:
           return jsonify({"message": f"No data found for department '{department}'"}), 404


       # Format the result into JSON and return
       response = []
       for row in result:
           response.append({
               "department": row[0],
               "employee_id": row[1],
               "employee_name": row[2],
               "present_days_count": row[3],
               "total_working_days_count": row[4] if timeframe == 'monthly' else row[4],
               "attendance_percentage": row[5]
           })


       return jsonify(response)


   except Exception as e:
       print(f"Error executing query: {str(e)}")  # Log any exception
       return jsonify({"error": str(e)}), 500


   finally:
       cursor.close()
       conn.close()




if __name__ == '__main__':
    app.run(debug=True)
