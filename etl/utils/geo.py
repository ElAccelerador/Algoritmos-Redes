import math
def haversine_m(a,b):
    lat1, lon1 = a; lat2, lon2 = b
    R = 6371000.0
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    y = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(y))
