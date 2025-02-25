from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect, CSRFError

# Create the Flask application instance
app = Flask(__name__)
# Load configuration from the config.py file
app.config.from_pyfile('config.py')
# Initialize CSRF protection for form submissions
csrf = CSRFProtect(app)

# --------------------------------------------------------
# UPLOAD CONFIGURATION
# --------------------------------------------------------
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Ensure that the upload folder exists (creates it if it doesn't)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --------------------------------------------------------
# DATABASE SETUP
# --------------------------------------------------------
db = SQLAlchemy(app)

# Define the Transaction model for storing transaction data in the database
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    transaction_type = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    receipt_image = db.Column(db.String(200))

    def __repr__(self):
        return f'<Transaction {self.name}>'

# Create all database tables if they do not exist
with app.app_context():
    db.create_all()

# --------------------------------------------------------
# ROUTES
# --------------------------------------------------------

# Home page route renders the index.html template.
@app.route('/')
def index():
    return render_template('index.html')

# Route to add a new transaction via a POST request.
@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if request.method == 'POST':
        try:
            # Retrieve form data
            name = request.form['name']
            transaction_type = request.form['transaction_type']
            amount = float(request.form['amount'])
            date_time = datetime.strptime(request.form['date_time'], '%Y-%m-%dT%H:%M')
            
            # Handle file upload for the receipt image
            file = request.files['receipt']
            filename = secure_filename(file.filename)
            # Save the file to the designated uploads folder
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # Build the relative file path for storage in the database
            file_path = f"uploads/{filename}"

            # Create a new Transaction object with the provided data
            new_transaction = Transaction(
                name=name,
                transaction_type=transaction_type,
                amount=amount,
                date=date_time.date(),
                time=date_time.time(),
                receipt_image=file_path
            )
            # Add the new transaction to the session and commit to the database
            db.session.add(new_transaction)
            db.session.commit()

        except Exception as e:
            # Log any errors encountered during the transaction submission
            print(f"Error: {str(e)}")
        
        # Redirect the user back to the home page after submission
        return redirect(url_for('index'))
    
# Route to analyze transactions based on various search/filter options.
@csrf.exempt
@app.route('/analysis')
def analysis():
    # Retrieve query parameters from the URL
    search_query = request.args.get('search', '').strip()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search_type = request.args.get('search_type')

    # --------------------------------------------------------
    # 2. Transaction Date Search
    # --------------------------------------------------------
    # If the search type is for transactions and both start and end dates are provided,
    # perform a date range search.
    if search_type == 'transactions' and start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Redirect to default view if the date range is invalid (start > end)
            if start > end: 
                return redirect(url_for('analysis'))
            
            # Query the Transaction table for records between the specified dates
            search_results = Transaction.query.filter(
                Transaction.date.between(start, end)
            ).order_by(Transaction.date.desc()).all()
            
            # Render the analysis template with the search results
            return render_template('analysis.html',
                search_results=search_results,
                start_date=start_date,
                end_date=end_date,
                totals=None
            )
        except ValueError:
            # Redirect if the provided date format is invalid
            return redirect(url_for('analysis'))

    # --------------------------------------------------------
    # 2. Date-filtered Totals (Total Analytics View)
    # --------------------------------------------------------
    # If the search type is "totals" and dates are provided, calculate summary totals.
    if search_type == 'totals' and start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Redirect if start date is after end date
            if start > end: 
                return redirect(url_for('analysis'))
            
            # Calculate deposit totals within the date range
            deposits = db.session.query(db.func.sum(Transaction.amount)).filter(
                Transaction.transaction_type == 'deposit',
                Transaction.date.between(start, end)
            ).scalar() or 0
            
            # Calculate withdrawal totals within the date range
            withdrawals = db.session.query(db.func.sum(Transaction.amount)).filter(
                Transaction.transaction_type == 'withdrawal',
                Transaction.date.between(start, end)
            ).scalar() or 0
            
            # Calculate profit as the difference between deposits and withdrawals
            profit = deposits - withdrawals
            
            # Render the analysis template with the totals data
            return render_template('analysis.html',
                totals={
                    'deposits': deposits,
                    'withdrawals': withdrawals,
                    'profit': profit,
                    'start_date': start_date,
                    'end_date': end_date
                },
                search_results=None,
                search_query=None,
                start_date=request.args.get('start_date'),
                end_date=request.args.get('end_date')
            )
        except ValueError:
            # Redirect if date conversion fails
            return redirect(url_for('analysis'))

    # --------------------------------------------------------
    # 1. Name Search
    # --------------------------------------------------------
    # If the search type is "name" and a query is provided, perform a search based on the transaction name.
    if search_type == 'name' and search_query:
        search_results = Transaction.query.filter(
            Transaction.name.ilike(f'%{search_query}%')
        ).order_by(Transaction.date.desc()).all()
        
        # Render results for the name search
        return render_template('analysis.html',
            search_query=search_query,
            search_results=search_results,
            totals=None,
            start_date=None,
            end_date=None
        )

    # --------------------------------------------------------
    # 4. Default Totals (No filters)
    # --------------------------------------------------------
    # If no filters are applied, calculate overall totals for deposits, withdrawals, and profit.
    deposits = db.session.query(db.func.sum(Transaction.amount)).filter_by(transaction_type='deposit').scalar() or 0
    withdrawals = db.session.query(db.func.sum(Transaction.amount)).filter_by(transaction_type='withdrawal').scalar() or 0
    profit = deposits - withdrawals
    
    # Render the analysis template with default totals data
    return render_template('analysis.html',
        totals={
            'deposits': deposits,
            'withdrawals': withdrawals,
            'profit': profit
        },
        search_query=None,
        search_results=None,
        start_date=request.args.get('start_date'),
        end_date=request.args.get('end_date')
    )

# Run the Flask development server in debug mode when this script is executed directly.
if __name__ == '__main__':
    app.run(debug=True)