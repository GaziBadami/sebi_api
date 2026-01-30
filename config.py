import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'database': os.getenv('DB_NAME', 'sebi_ipo_db')
}

# API Configuration
API_KEY = os.getenv('API_KEY', '123456789')

# App Configuration
APP_NAME = "SEBI IPO API"
APP_VERSION = "1.0.0"