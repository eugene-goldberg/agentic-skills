from fastapi import FastAPI

from app.database import Base, engine
from app.routers import auth, me

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Project Tracker v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(me.router)
