from fastapi import FastAPI

from .router import router


def create_project7_app() -> FastAPI:
    app = FastAPI(title='Project 7 RAG PDF Chat (Isolated)')
    app.include_router(router)

    @app.get('/healthz')
    async def healthz() -> dict[str, str]:
        return {'status': 'ok'}

    return app


app = create_project7_app()
