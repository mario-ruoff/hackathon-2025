import uvicorn
import pandas as pd
from keplergl import KeplerGl 
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

df = pd.read_csv("kepler_test.csv")

kepler = KeplerGl(height=600)
kepler.add_data(data=df, name="Test Data")
app = FastAPI()

html = kepler._repr_html_()

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=html)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
