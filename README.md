# Flight history fullstack app
This app is getting flight data from opensky service and plane data into postgres database. This is happening in the background separately from fastapi.
Webapi to be used web map front service is served using fastapi. NextJS front polls the newest batch (finalized batch) every 10 sec and update 
plane locations on the map.

techs: fastapi, postgresql, nextjs, openlayers, leaflet

## running the api
uvicorn api:app --host 0.0.0.0 --port 8001
