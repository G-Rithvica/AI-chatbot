import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def check_connection(connection_url=""):
    engine = create_async_engine(connection_url, connect_args={"timeout": 5})
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version();"))
            version = result.scalar()
            print(f"Connected to Supabase successfully!\nPostgreSQL version: {version}")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(
        check_connection(
            connection_url="postgresql+asyncpg://postgres.gagczbqbzxdhucuxlrny:gJN6dk6Bd+eZsHh@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres",
        )
    )