import asyncio
from sqlalchemy import text
from app.database import engine, Base
from app.models.user import User

async def run_migrations():
    async with engine.begin() as conn:
        # Check if the is_active column exists
        result = await conn.execute(
            text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='is_active';
            """)
        )
        
        # If the column doesn't exist, add it
        if not result.scalar():
            print("Adding is_active column to users table...")
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE;")
            )
            print("Successfully added is_active column.")
        else:
            print("is_active column already exists.")

if __name__ == "__main__":
    asyncio.run(run_migrations())
