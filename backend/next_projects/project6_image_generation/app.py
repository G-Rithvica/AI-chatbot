from fastapi import FastAPI

from .router import router


def create_project6_app() -> FastAPI:
    app = FastAPI(title='Project 6 Image Generation (Isolated)')
    app.include_router(router)

    @app.get('/healthz')
    async def healthz() -> dict[str, str]:
        return {'status': 'ok'}

    return app


app = create_project6_app()
