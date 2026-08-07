from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests

Base = declarative_base()

class SingaporeData(Base):
    __tablename__ = 'singapore_data'

    id = Column(Integer, primary_key=True, index=True)
    data_field_1 = Column(String, index=True)
    data_field_2 = Column(Float)
    data_field_3 = Column(String)

DATABASE_URL = "postgresql://user:password@localhost/dbname"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def fetch_singapore_data():
    response = requests.get("https://api.example.com/singapore")
    if response.status_code == 200:
        return response.json()
    return None

def process_singapore_data(data):
    # Implement data processing logic here
    processed_data = []
    for item in data:
        processed_data.append(SingaporeData(
            data_field_1=item['field1'],
            data_field_2=item['field2'],
            data_field_3=item['field3']
        ))
    return processed_data

def save_data_to_db(data):
    db = SessionLocal()
    try:
        db.add_all(data)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()