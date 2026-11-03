import os
import threading

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .analysis import analyze
from .data import DATASET_ID, catalog

ENGINE = os.environ.get('CHANLUN_ENGINE', 'chanpy')
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
gate = threading.BoundedSemaphore(1)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    datasetId: str
    observedBars: int = Field(ge=50, le=5000)


@app.get('/health')
def health():
    return {'status': 'UP', 'engine': ENGINE, 'dataset': catalog()}


@app.post('/internal/v1/analyze')
def run(request: AnalyzeRequest):
    if request.datasetId != DATASET_ID:
        raise HTTPException(422, 'Unknown frozen dataset')
    if not gate.acquire(blocking=False):
        raise HTTPException(429, 'Engine is busy; retry after the current calculation')
    try:
        return analyze(ENGINE, request.observedBars)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    finally:
        gate.release()
