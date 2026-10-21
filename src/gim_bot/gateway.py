import hmac
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import Field

from .analysis import Provider, StrictModel
from .config import get_settings


class AnalysisRequest(StrictModel):
    answers: dict[str, Annotated[str, Field(max_length=10000)]] = Field(max_length=30)


class FollowupRequest(AnalysisRequest):
    library: list[dict[str, str]] = Field(max_length=4)


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    app.state.provider = Provider(settings)
    try:
        yield
    finally:
        await app.state.provider.close()


app = FastAPI(title='GIM internal LLM gateway', lifespan=lifespan, docs_url=None, redoc_url=None)


async def authorize(x_internal_key: str = Header(default='')):
    expected = get_settings().internal_api_key
    if not expected or not hmac.compare_digest(x_internal_key, expected):
        raise HTTPException(403, 'Доступ запрещён')


@app.get('/health')
async def health():
    return {'status': 'ok'}


@app.post('/analyze', dependencies=[Depends(authorize)])
async def analyze(body: AnalysisRequest):
    return {'result': await app.state.provider.analyze(body.answers)}


@app.post('/followups', dependencies=[Depends(authorize)])
async def followups(body: FollowupRequest):
    return {'result': await app.state.provider.followups(body.answers, body.library)}
