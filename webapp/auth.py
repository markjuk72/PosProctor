"""
Authentication module for POSProctor
Supports: No authentication or Microsoft Entra ID (Azure AD) SSO
"""
import os
from functools import wraps
from flask import redirect, url_for, session, request, flash
from flask_login import LoginManager, UserMixin, current_user
import msal

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

# Authentication configuration
# AUTH_TYPE: 'none' or 'entra'
AUTH_TYPE = os.getenv('AUTH_TYPE', 'none')

# Microsoft Entra ID (Azure AD) configuration
ENTRA_CLIENT_ID = os.getenv('ENTRA_CLIENT_ID', '')
ENTRA_CLIENT_SECRET = os.getenv('ENTRA_CLIENT_SECRET', '')
ENTRA_TENANT_ID = os.getenv('ENTRA_TENANT_ID', '')
ENTRA_REDIRECT_URI = os.getenv('ENTRA_REDIRECT_URI', '')

def init_auth(app):
    """Initialize authentication for the Flask app"""
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'

    @login_manager.user_loader
    def load_user(user_id):
        # Load user from session
        username = session.get('username')
        if username:
            return User(user_id, username)
        return None

    return login_manager

def get_msal_app():
    """Get MSAL application for Entra authentication"""
    if not ENTRA_CLIENT_ID or not ENTRA_TENANT_ID:
        return None

    authority = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}"
    return msal.ConfidentialClientApplication(
        ENTRA_CLIENT_ID,
        authority=authority,
        client_credential=ENTRA_CLIENT_SECRET
    )

def login_required_conditional(f):
    """Decorator that enforces login only if AUTH_TYPE is 'entra'"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if AUTH_TYPE == 'entra' and not current_user.is_authenticated:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def protected_route(f):
    """Decorator that ALWAYS requires authentication when AUTH_TYPE='entra'

    Use this for routes that should be protected when authentication is enabled.
    Public routes (like dashboard, transactions) should not use this decorator.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if AUTH_TYPE == 'entra':
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'info')
                return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_auth_config():
    """Get authentication configuration for display"""
    return {
        'enabled': AUTH_TYPE == 'entra',
        'type': AUTH_TYPE,
        'entra_enabled': AUTH_TYPE == 'entra' and bool(ENTRA_CLIENT_ID and ENTRA_TENANT_ID),
        'entra_configured': bool(ENTRA_CLIENT_ID and ENTRA_TENANT_ID)
    }
