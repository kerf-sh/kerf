from fastapi import FastAPI

from cloud.pyworker.routes import fem, spice, topo

app = FastAPI()

app.include_router(fem.router, prefix="", tags=["fem"])
app.include_router(spice.router, prefix="", tags=["spice"])
app.include_router(topo.router, prefix="", tags=["topo"])
app.include_router(cam.router, prefix="", tags=["cam"])
app.include_router(ifc.router, prefix="", tags=["ifc"])
app.include_router(import_kicad.router, prefix="", tags=["import"])
app.include_router(import_freecad.router, prefix="", tags=["import"])
app.include_router(rf.router, prefix="", tags=["rf"])

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}