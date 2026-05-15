from fastapi import APIRouter

from app.api.routes.attachments import router as attachments_router
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.database_chat import router as database_chat_router
from app.api.routes.image_generation import router as image_generation_router
from app.api.routes.threads import router as threads_router
from next_projects.project6_image_generation.router import router as project6_router
from next_projects.project7_rag.router import router as project7_router
from next_projects.project8_data_qa.router import router as project8_router
from next_projects.project9_sheets_query_agent.router import router as project9_router
from next_projects.project10_research_digest.router import router as project10_router
from next_projects.project11_tic_tac_toe_agent.router import router as project11_router
from next_projects.project12_mcp_research.router import router as project12_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix='/auth', tags=['auth'])
api_router.include_router(chat_router, prefix='/chat', tags=['chat'])
api_router.include_router(threads_router, prefix='/threads', tags=['threads'])
api_router.include_router(attachments_router, prefix='/attachments', tags=['attachments'])
api_router.include_router(database_chat_router)
api_router.include_router(image_generation_router, prefix='/image-generation', tags=['image-generation'])
api_router.include_router(project6_router)
api_router.include_router(project7_router)
api_router.include_router(project8_router)
api_router.include_router(project9_router)
api_router.include_router(project10_router)
api_router.include_router(project11_router)
api_router.include_router(project12_router)
