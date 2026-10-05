import os
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env SEBELUM apapun yang baca os.environ.
# Path: main.py ada di backend/, .env ada di root project (1 level di atas).
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from routes.analytics import analytics_router
from routes.clay_engine import clay_router

# Logger biar traceback muncul di terminal server (bukan cuma 500 generic)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nasuha")

frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend'))

# docs_url/redoc_url di-disable: jangan ekspos skema API publik
app = FastAPI(title="Nasuha Web API", docs_url=None, redoc_url=None, openapi_url=None)


# ---------------------------------------------------------------------------
# CORS: batasi origin di production
# ---------------------------------------------------------------------------
_dev = os.environ.get('FLASK_ENV', 'production').lower() == 'development'
_allowed_origins = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', '').split(',') if o.strip()]

if _dev:
    _origins = ["*"]
elif _allowed_origins:
    _origins = _allowed_origins
else:
    _origins = []  # production tanpa ALLOWED_ORIGINS → tidak ada cross-origin

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Security headers global
# ---------------------------------------------------------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    resp.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    return resp


# ---------------------------------------------------------------------------
# Exception handler: samakan format error dengan yang diharapkan frontend
#   { "status": "error", "message": "<detail>" }
#
# FIX BUG #3: kalau exc.detail berupa list (dari validasi Pydantic 422),
# ringkas jadi string. Tanpa ini, frontend render "[object Object]".
# ---------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail

    if isinstance(detail, list):
        # Format Pydantic: [{"loc": [...], "msg": "...", "type": "..."}, ...]
        parts = []
        for d in detail:
            if isinstance(d, dict):
                loc = ".".join(str(x) for x in d.get("loc", []))
                msg = d.get("msg", "invalid")
                parts.append(f"{loc}: {msg}" if loc else msg)
            else:
                parts.append(str(d))
        detail = "; ".join(parts) if parts else "Validasi gagal"

    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": str(detail)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log traceback lengkap ke server, jangan ke client.
    logger.exception("Unhandled error at %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Terjadi kesalahan pada server"},
    )


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
app.include_router(analytics_router, prefix="/api")
app.include_router(clay_router, prefix="/api/clay")


# ---------------------------------------------------------------------------
# SPA + static files
# ---------------------------------------------------------------------------
@app.get("/")
async def root_index():
    return FileResponse(os.path.join(frontend_folder, "index.html"))


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    # /api/* yang tidak match router → JSON 404 (bukan index.html)
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Endpoint API tidak ditemukan"},
        )

    # Path traversal guard
    static_root = os.path.realpath(frontend_folder)
    target = os.path.realpath(os.path.join(frontend_folder, full_path))
    if target != static_root and not target.startswith(static_root + os.sep):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Path tidak valid"},
        )

    # File fisik (css/js/png/html component) → sajikan langsung
    if full_path and os.path.isfile(target):
        resp = FileResponse(target)
        # Paksa browser selalu cek ulang file statis (HTML/CSS/JS)
        if target.endswith(('.html', '.css', '.js')):
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
        return resp

    # Route SPA / halaman web → index.html
    return FileResponse(os.path.join(frontend_folder, "index.html"))


if __name__ == '__main__':
    import uvicorn
    reload_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    uvicorn.run("main:app", host='127.0.0.1', port=8080, reload=reload_mode)
