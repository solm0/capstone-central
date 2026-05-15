import os

import stanza
import classla

from db import engine, Base
from packs import PACKS

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers.auth_router import router as auth_router
from routers.pages_router import router as pages_router
from routers.lemmas_router import router as lemmas_router
from routers.mutual_router import router as mutual_router
from routers.comment_router import router as comment_router
from routers.internal_router import router as internal_router
from routers.mobile_router import router as mobile_router

MODEL_DIR = "./models"
CLASSLA_LANGS = {"sr", "mk"}

app = FastAPI()

# stanza 모델 설치
def ensure_language_models():
    os.makedirs(MODEL_DIR, exist_ok=True)

    downloaded = set()

    for pack in PACKS:
        lang = pack["lang"]

        if lang in downloaded:
            continue

        downloaded.add(lang)

        try:
            if lang in CLASSLA_LANGS:
                print(f"[classla] ensuring model: {lang}")

                classla.download(
                    lang,
                    dir=MODEL_DIR,
                )

            else:
                print(f"[stanza] ensuring model: {lang}")

                stanza.download(
                    lang,
                    model_dir=MODEL_DIR,
                )

        except Exception as e:
            print(f"Failed downloading {lang}: {e}")


ensure_language_models()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "http://localhost",
        "https://localhost",
        "capacitor://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(lemmas_router)
app.include_router(mutual_router)
app.include_router(comment_router)
app.include_router(internal_router)
app.include_router(mobile_router)

Base.metadata.create_all(bind=engine)
