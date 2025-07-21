import mysql, mysql.connector
from mysql.connector import errorcode


hostname = "localhost"
db       = "HorizonTravels"
username = "root"
passwd   = "50125012" 

def getConnection():
    try: 
        conn = mysql.connector.connect(host=hostname,
                                       user=username,
                                       password=passwd,
                                       database=db) #database optional
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print('Username or Password is incorrect')
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print('Data base does not exist')
        else:
            print(err)
    else: #will execute if there is no exception raised in try block
        return conn