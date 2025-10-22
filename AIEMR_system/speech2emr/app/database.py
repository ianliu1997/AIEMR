from sqlmodel import SQLModel, create_engine, Session
from .settings import settings

engine = create_engine(settings.DB_URL, echo=False, future=True)



def get_session():
    with Session(engine) as session:
        yield session

# Optional: For explicit compatibility
Base = SQLModel
