from sqlalchemy import *
from utils.db.db_config import get_db_engine
meta = MetaData()
# conn_str = (f"mysql+mysqlconnector://{self.db_username}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}""?connect_timeout=0")
engine = get_db_engine('HK_HK4030', '6')
print("TABLE CREATING")

pms_wise_hotel_key_res = Table(
    'pms_wise_hotel_key_res', meta,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('propertyCode', String(20)),
    Column('pullDateId', String(20)),
    Column('AsOfDate', Date()),
    Column('BookingInfo', String(55)),
    Column('BookingTime', String(55)),
    Column('ConfirmationNo', String(55)),
    Column('GuestName', String(55)),
    Column('ArrivalDate', String(55)),
    Column('Nights', String(55)),
    Column('RoomType', String(55)),
    Column('Source', String(55)),
    Column('RateCode', String(55)),
    Column('RoomRent', String(55)),
    Column('Status', String(55)),
    Column('CancellationDate', String(55)),
    Column('BookedBy', String(55))
)

print("TABLE CREATED SUCCESSFULLY")
meta.create_all(engine)
