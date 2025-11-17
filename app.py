import os
import time
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Use PostgreSQL from Render
database_url = os.environ.get('DATABASE_URL')

if not database_url:
    raise ValueError("DATABASE_URL environment variable is required")

# Fix the URL format for SQLAlchemy + force psycopg3
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)


app.config['SQLALCHEMY_DATABASE_URI'] = database_url
print(f"✅ Using PostgreSQL with psycopg3")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(15))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    listings = db.relationship('Listing', backref='owner', lazy=True)

class Listing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    rental_period = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(100), nullable=False, default='Gadhinglaj')
    images = db.Column(db.Text)
    contact_number = db.Column(db.String(15), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_featured = db.Column(db.Boolean, default=False)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_database():
    """Initialize database with retry logic"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with app.app_context():
                db.create_all()
                # Create sample user if no users exist
                if not User.query.first():
                    sample_user = User(
                        username='demo',
                        email='demo@example.com',
                        password=generate_password_hash('password'),
                        phone='1234567890'
                    )
                    db.session.add(sample_user)
                    db.session.commit()
                    print("✅ Database initialized with sample user")
                else:
                    print("✅ Database already initialized")
                return True
        except Exception as e:
            print(f"❌ Database initialization attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait 2 seconds before retry
            else:
                print("❌ All database initialization attempts failed")
                return False

# Initialize database when app starts
print("🔄 Initializing database...")
if init_database():
    print("✅ Database initialization successful")
else:
    print("❌ Database initialization failed")

# Routes
@app.route('/')
def index():
    try:
        # Try to get listings, but handle case where tables might not exist yet
        featured_listings = Listing.query.filter_by(is_featured=True).order_by(Listing.created_at.desc()).limit(2).all()
        recent_listings = Listing.query.order_by(Listing.created_at.desc()).limit(8).all()
        return render_template('index.html', featured_listings=featured_listings, recent_listings=recent_listings)
    except Exception as e:
        print(f"⚠️ Error loading listings: {e}")
        # Return empty listings if there's an error
        return render_template('index.html', featured_listings=[], recent_listings=[])

@app.route('/my_ads')
def my_ads():
    if 'user_id' not in session:
        flash('Please login to view your ads', 'error')
        return redirect(url_for('login'))
    
    try:
        user_listings = Listing.query.filter_by(user_id=session['user_id']).order_by(Listing.created_at.desc()).all()
        return render_template('my_ads.html', listings=user_listings)
    except Exception as e:
        print(f"Error loading user ads: {e}")
        flash('Error loading your ads', 'error')
        return render_template('my_ads.html', listings=[])

@app.route('/rent_out', methods=['GET', 'POST'])
def rent_out():
    if request.method == 'POST':
        if 'user_id' not in session:
            flash('Please login to post an ad', 'error')
            return redirect(url_for('login'))
        
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        price = request.form.get('price')
        rental_period = request.form.get('rental_period')
        location = request.form.get('location', 'Gadhinglaj')
        contact_number = request.form.get('contact_number')
        
        if not all([title, description, category, price, rental_period, contact_number]):
            flash('Please fill all required fields', 'error')
            return render_template('rent_out.html')
        
        image_files = request.files.getlist('images')
        uploaded_images = []
        
        for image in image_files:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                filename = timestamp + filename
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)
                uploaded_images.append(filename)
        
        try:
            new_listing = Listing(
                title=title,
                description=description,
                price=float(price),
                rental_period=rental_period,
                category=category,
                location=location,
                images=json.dumps(uploaded_images) if uploaded_images else '[]',
                contact_number=contact_number,
                user_id=session['user_id']
            )
            
            db.session.add(new_listing)
            db.session.commit()
            
            flash('Your rental ad has been posted successfully!', 'success')
            return redirect(url_for('my_ads'))
        except Exception as e:
            print(f"Error creating listing: {e}")
            flash('Error creating your ad. Please try again.', 'error')
            return render_template('rent_out.html')
    
    return render_template('rent_out.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            user = User.query.filter_by(email=email).first()
            
            if user and check_password_hash(user.password, password):
                session['user_id'] = user.id
                session['username'] = user.username
                flash('Login successful!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid email or password', 'error')
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login error. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        phone = request.form.get('phone')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        
        try:
            if User.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
                return render_template('register.html')
            
            if User.query.filter_by(username=username).first():
                flash('Username already taken', 'error')
                return render_template('register.html')
            
            new_user = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
                phone=phone
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration error. Please try again.', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '')
    location = request.args.get('location', 'Gadhinglaj')
    category = request.args.get('category', '')
    
    try:
        listings_query = Listing.query
        
        if query:
            listings_query = listings_query.filter(
                db.or_(
                    Listing.title.ilike(f'%{query}%'),
                    Listing.description.ilike(f'%{query}%')
                )
            )
        
        if location and location != 'all':
            listings_query = listings_query.filter(Listing.location == location)
        
        if category and category != 'all':
            listings_query = listings_query.filter(Listing.category == category)
        
        listings = listings_query.order_by(Listing.created_at.desc()).all()
        
        return render_template('search.html', 
                             listings=listings, 
                             query=query,
                             location=location,
                             category=category)
    except Exception as e:
        print(f"Search error: {e}")
        return render_template('search.html', listings=[], query=query, location=location, category=category)

@app.route('/edit_ad/<int:ad_id>', methods=['GET', 'POST'])
def edit_ad(ad_id):
    if 'user_id' not in session:
        flash('Please login to edit your ad', 'error')
        return redirect(url_for('login'))
    
    listing = Listing.query.get_or_404(ad_id)
    
    # Check if the current user owns this listing
    if listing.user_id != session['user_id']:
        flash('You can only edit your own ads', 'error')
        return redirect(url_for('my_ads'))
    
    if request.method == 'POST':
        try:
            listing.title = request.form.get('title')
            listing.description = request.form.get('description')
            listing.category = request.form.get('category')
            listing.price = float(request.form.get('price'))
            listing.rental_period = request.form.get('rental_period')
            listing.location = request.form.get('location', 'Gadhinglaj')
            listing.contact_number = request.form.get('contact_number')
            
            # Handle image updates
            image_files = request.files.getlist('images')
            uploaded_images = []
            
            for image in image_files:
                if image and allowed_file(image.filename):
                    filename = secure_filename(image.filename)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                    filename = timestamp + filename
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    image.save(image_path)
                    uploaded_images.append(filename)
            
            if uploaded_images:
                # Merge with existing images
                existing_images = json.loads(listing.images) if listing.images else []
                existing_images.extend(uploaded_images)
                listing.images = json.dumps(existing_images)
            
            db.session.commit()
            flash('Ad updated successfully!', 'success')
            return redirect(url_for('my_ads'))
            
        except Exception as e:
            print(f"Error updating listing: {e}")
            flash('Error updating your ad. Please try again.', 'error')
    
    # Prepare images for template
    images = []
    if listing.images:
        try:
            images = json.loads(listing.images)
        except:
            images = []
    
    # Pass both 'listing' and 'ad' variables to template for compatibility
    return render_template('edit_ad.html', listing=listing, ad=listing, images=images)

@app.route('/delete_ad/<int:ad_id>', methods=['POST'])
def delete_ad(ad_id):
    if 'user_id' not in session:
        flash('Please login to delete your ad', 'error')
        return redirect(url_for('login'))
    
    listing = Listing.query.get_or_404(ad_id)
    
    # Check if the current user owns this listing
    if listing.user_id != session['user_id']:
        flash('You can only delete your own ads', 'error')
        return redirect(url_for('my_ads'))
    
    try:
        # Delete associated images from filesystem
        if listing.images:
            images = json.loads(listing.images)
            for image in images:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image)
                if os.path.exists(image_path):
                    os.remove(image_path)
        
        db.session.delete(listing)
        db.session.commit()
        flash('Ad deleted successfully!', 'success')
    except Exception as e:
        print(f"Error deleting listing: {e}")
        flash('Error deleting your ad. Please try again.', 'error')
    
    return redirect(url_for('my_ads'))

# Template filters
@app.template_filter('time_ago')
def time_ago_filter(dt):
    if not dt: return 'Recently'
    now = datetime.utcnow()
    diff = now - dt
    if diff.days > 365:
        years = diff.days // 365
        return f'{years} year{"s" if years > 1 else ""} ago'
    elif diff.days > 30:
        months = diff.days // 30
        return f'{months} month{"s" if months > 1 else ""} ago'
    elif diff.days > 0:
        return f'{diff.days} day{"s" if diff.days > 1 else ""} ago'
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f'{hours} hour{"s" if hours > 1 else ""} ago'
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
    else:
        return 'Just now'

@app.template_filter('format_price')
def format_price_filter(price):
    return f'{price:,.0f}'

@app.template_filter('get_first_image')
def get_first_image_filter(images_json):
    if images_json:
        try:
            images = json.loads(images_json)
            if images and len(images) > 0:
                return url_for('static', filename=f'uploads/{images[0]}')
        except:
            pass
    return url_for('static', filename='images/placeholder.jpg')

@app.context_processor
def inject_user():
    return dict(session=session)

@app.route('/main.css')
def serve_css():
    return app.send_static_file('main.css')

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
