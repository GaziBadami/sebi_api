from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from database import get_database_connection, close_connection
from auth import verify_api_key
from config import APP_NAME, APP_VERSION
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title=APP_NAME,
    description="Secure API to fetch IPO filing data from SEBI with authentication",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public endpoint - No authentication required
@app.get("/")
def home():
    """Welcome page - Public access"""
    return {
        "message": f"Welcome to {APP_NAME}",
        "version": APP_VERSION,
        "status": "online",
        "authentication": "Required for all endpoints except /health",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc"
        },
        "note": "Include 'X-API-Key' header in all requests"
    }

# Health check - No authentication required
@app.get("/health")
def health_check():
    """Check if API and database are working - Public access"""
    conn = get_database_connection()
    if conn:
        close_connection(conn)
        return {"status": "healthy", "database": "connected"}
    else:
        return {"status": "unhealthy", "database": "disconnected"}

# Protected endpoints - Require API key
@app.get("/ipos")
@limiter.limit("100/minute")
def get_ipos(request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    company: Optional[str] = Query(None, description="Search by company name"),
    date: Optional[str] = Query(None, description="Filter by filing date (DD/MM/YYYY)"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get list of IPOs with pagination and optional filters
    
    **Authentication Required**: Include X-API-Key header
    
    **Rate Limit**: 100 requests per minute
    """
    
    logger.info(f"GET /ipos - page={page}, limit={limit}, company={company}, date={date}")
    
    conn = get_database_connection()
    if not conn:
        logger.error("Database connection failed")
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Build query
        query = "SELECT filing_date, company_name, pdf_urls FROM ipos WHERE 1=1"
        params = []
        
        if company:
            query += " AND company_name LIKE %s"
            params.append(f"%{company}%")
        
        if date:
            query += " AND filing_date = %s"
            params.append(date)
        
        # Get total count
        count_query = query.replace("SELECT filing_date, company_name, pdf_urls", "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['COUNT(*)']
        
        # Add pagination
        offset = (page - 1) * limit
        query += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        # Execute
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Format response
        ipos = [
            {
                "filing_date": row['filing_date'],
                "company_name": row['company_name'],
                "pdf_url": row['pdf_urls']
            }
            for row in results
        ]
        
        cursor.close()
        close_connection(conn)
        
        logger.info(f"Returned {len(ipos)} IPOs")
        
        return {
            "total": total_count,
            "page": page,
            "limit": limit,
            "total_pages": (total_count + limit - 1) // limit,
            "data": ipos
        }
    
    except Exception as e:
        logger.error(f"Error in get_ipos: {str(e)}")
        close_connection(conn)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/ipos/{ipo_id}")
@limiter.limit("100/minute")

def get_ipo_by_id(request: Request,

    ipo_id: int,
    api_key: str = Depends(verify_api_key)
):
    """
    Get a single IPO by its ID
    
    **Authentication Required**: Include X-API-Key header
    """
    
    logger.info(f"GET /ipos/{ipo_id}")
    
    conn = get_database_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT filing_date, company_name, pdf_urls FROM ipos WHERE id = %s"
        cursor.execute(query, (ipo_id,))
        result = cursor.fetchone()
        
        cursor.close()
        close_connection(conn)
        
        if not result:
            raise HTTPException(status_code=404, detail="IPO not found")
        
        return {
            "filing_date": result['filing_date'],
            "company_name": result['company_name'],
            "pdf_url": result['pdf_urls']
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_ipo_by_id: {str(e)}")
        close_connection(conn)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/ipos/latest")
@limiter.limit("100/minute")

def get_latest_ipos(request: Request,

    limit: int = Query(10, ge=1, le=100, description="Number of latest IPOs"),
    api_key: str = Depends(verify_api_key)
):
    """
    Get the most recent IPO filings
    
    **Authentication Required**: Include X-API-Key header
    """
    
    logger.info(f"GET /ipos/latest - limit={limit}")
    
    conn = get_database_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT filing_date, company_name, pdf_urls 
            FROM ipos 
            ORDER BY id DESC 
            LIMIT %s
        """
        cursor.execute(query, (limit,))
        results = cursor.fetchall()
        
        cursor.close()
        close_connection(conn)
        
        ipos = [
            {
                "filing_date": row['filing_date'],
                "company_name": row['company_name'],
                "pdf_url": row['pdf_urls']
            }
            for row in results
        ]
        
        return {
            "count": len(ipos),
            "data": ipos
        }
    
    except Exception as e:
        logger.error(f"Error in get_latest_ipos: {str(e)}")
        close_connection(conn)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")