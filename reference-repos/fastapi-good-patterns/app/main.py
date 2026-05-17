from fastapi import FastAPI

from app.routers import health, auth, me, workspaces, projects, tasks
from app.database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Project Tracker v1")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(workspaces.router)
app.include_router(projects.router)
app.include_router(tasks.router)
