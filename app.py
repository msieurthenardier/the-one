from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json

from the_one import __version__

app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost:8000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)

@app.get("/api/info")
def info():
    return {
        'name': 'The One',
        'description': 'A personal AI agent.',
        'version': __version__
    }

@app.get("/api/health")
def health():
    return {'status': 'ok', 'version': __version__}
