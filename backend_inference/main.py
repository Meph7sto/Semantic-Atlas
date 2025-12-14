import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI

# Ensure we can import from local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.model_container import model_engine
from core.config import settings
from routers import conflict

# You can easily import other routers here in the future
# from routers import classification, traceability

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load the model
    print(f"Initializing Model from: {settings.MODEL_PATH}")
    if os.path.exists(settings.MODEL_PATH):
        try:
            model_engine.load_model()
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load model files: {e}")
            # We continue startup so health checks pass, but inference will fail
    else:
        print(f"CRITICAL WARNING: Model directory not found at {settings.MODEL_PATH}")
    yield
    # Shutdown logic if needed

app = FastAPI(
    title="Semantic Atlas Inference API", 
    version="1.0",
    description="Backend inference service for requirement analysis.",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(conflict.router)
# app.include_router(classification.router)
# app.include_router(traceability.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "model_loaded": model_engine.model is not None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
