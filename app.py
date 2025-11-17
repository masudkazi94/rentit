from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///marketplace.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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
    rental_period = db.Column(db.String(20), nullable=False)  # day, week, month
    category = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(100), nullable=False, default='Gadhinglaj')
    images = db.Column(db.Text)  # JSON string of image filenames
    contact_number = db.Column(db.String(15), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_featured = db.Column(db.Boolean, default=False)

# Allowed file extensions for images
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def index():
    # Get featured listings
    featured_listings = Listing.query.filter_by(is_featured=True).order_by(Listing.created_at.desc()).limit(2).all()
    
    # Get recent listings
    recent_listings = Listing.query.order_by(Listing.created_at.desc()).limit(8).all()
    
    return render_template('index.html', 
                         featured_listings=featured_listings,
                         recent_listings=recent_listings)

# Remove categories route since we don't need it in navigation anymore
# @app.route('/categories')
# def categories():
#     # Get all unique categories with count
#     categories_data = db.session.query(
#         Listing.category,
#         db.func.count(Listing.id)
#     ).group_by(Listing.category).all()
#     
#     return render_template('categories.html', categories=categories_data)

# Add My Ads route
@app.route('/my_ads')
def my_ads():
    if 'user_id' not in session:
        flash('Please login to view your ads', 'error')
        return redirect(url_for('login'))
    
    user_listings = Listing.query.filter_by(user_id=session['user_id']).order_by(Listing.created_at.desc()).all()
    return render_template('my_ads.html', listings=user_listings)

# Update sell route name for consistency
@app.route('/rent_out', methods=['GET', 'POST'])
def rent_out():
    if request.method == 'POST':
        # Check if user is logged in
        if 'user_id' not in session:
            flash('Please login to post an ad', 'error')
            return redirect(url_for('login'))
        
        # Get form data
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        price = request.form.get('price')
        rental_period = request.form.get('rental_period')
        location = request.form.get('location', 'Gadhinglaj')
        contact_number = request.form.get('contact_number')
        
        # Validate required fields
        if not all([title, description, category, price, rental_period, contact_number]):
            flash('Please fill all required fields', 'error')
            return render_template('rent_out.html')
        
        # Handle image uploads
        image_files = request.files.getlist('images')
        uploaded_images = []
        
        for image in image_files:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                # Add timestamp to make filename unique
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                filename = timestamp + filename
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)
                uploaded_images.append(filename)
        
        # Create new listing
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
    
    return render_template('rent_out.html')

# Add edit ad route
@app.route('/edit_ad/<int:ad_id>', methods=['GET', 'POST'])
def edit_ad(ad_id):
    if 'user_id' not in session:
        flash('Please login to edit ads', 'error')
        return redirect(url_for('login'))
    
    ad = Listing.query.get_or_404(ad_id)
    
    # Check if user owns the ad
    if ad.user_id != session['user_id']:
        flash('You can only edit your own ads', 'error')
        return redirect(url_for('my_ads'))
    
    if request.method == 'POST':
        # Update ad data
        ad.title = request.form.get('title')
        ad.description = request.form.get('description')
        ad.category = request.form.get('category')
        ad.price = float(request.form.get('price'))
        ad.rental_period = request.form.get('rental_period')
        ad.location = request.form.get('location', 'Gadhinglaj')
        ad.contact_number = request.form.get('contact_number')
        
        # Handle new image uploads
        image_files = request.files.getlist('images')
        uploaded_images = json.loads(ad.images) if ad.images else []
        
        for image in image_files:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                filename = timestamp + filename
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)
                uploaded_images.append(filename)
        
        ad.images = json.dumps(uploaded_images)
        
        db.session.commit()
        flash('Ad updated successfully!', 'success')
        return redirect(url_for('my_ads'))
    
    images = json.loads(ad.images) if ad.images else []
    return render_template('edit_ad.html', ad=ad, images=images)

# Add delete ad route
@app.route('/delete_ad/<int:ad_id>')
def delete_ad(ad_id):
    if 'user_id' not in session:
        flash('Please login to delete ads', 'error')
        return redirect(url_for('login'))
    
    ad = Listing.query.get_or_404(ad_id)
    
    # Check if user owns the ad
    if ad.user_id != session['user_id']:
        flash('You can only delete your own ads', 'error')
        return redirect(url_for('my_ads'))
    
    # Delete associated images
    if ad.images:
        images = json.loads(ad.images)
        for image in images:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image)
            if os.path.exists(image_path):
                os.remove(image_path)
    
    db.session.delete(ad)
    db.session.commit()
    
    flash('Ad deleted successfully', 'success')
    return redirect(url_for('my_ads'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        phone = request.form.get('phone')
        
        # Validation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
            return render_template('register.html')
        
        # Create new user
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
    
    # Build query
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

# Custom template filters
@app.template_filter('time_ago')
def time_ago_filter(dt):
    if not dt:
        return 'Recently'
        
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

# Add this context processor to make session available in all templates
@app.context_processor
def inject_user():
    return dict(session=session)

# Serve static files correctly
@app.route('/main.css')
def serve_css():
    return app.send_static_file('main.css')

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# Initialize database
def init_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        
        # Create a sample user for testing
        if not User.query.first():
            sample_user = User(
                username='demo',
                email='demo@example.com',
                password=generate_password_hash('password'),
                phone='1234567890'
            )
            db.session.add(sample_user)
            db.session.commit()
            print("Sample user created:")
            print("Username: demo")
            print("Password: password")
            print("Email: demo@example.com")

if __name__ == '__main__':
    init_db()
    app.run(debug=True)