from typing import Annotated

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase as Base
from sqlalchemy.orm import declarative_base, mapped_column

DeclarativeBase: type[Base] = declarative_base()

intpk = Annotated[int, mapped_column(primary_key=True, autoincrement=True)]
str10 = Annotated[str, mapped_column(String(10))]
str20 = Annotated[str, mapped_column(String(20))]
str50 = Annotated[str, mapped_column(String(50))]
