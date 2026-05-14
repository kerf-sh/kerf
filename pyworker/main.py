from fastapi import FastAPI

# Routes still in pyworker
from pyworker.routes import fem, topo, cam, mates

# tess route migrated to kerf-tess plugin; import from new location.
try:
    from kerf_tess.routes import router as _tess_router
    _tess_from_plugin = True
except ImportError:
    # Fallback: kerf-tess not installed — route will be absent.
    _tess_router = None
    _tess_from_plugin = False

# Routes migrated to plugin packages
from kerf_bim.routes import router as bim_router
from kerf_electronics.routes_rf import router as rf_router
from kerf_electronics.routes_spice import router as spice_router
from kerf_electronics.routes_autoroute import router as autoroute_router
from kerf_electronics.routes_pour import router as pour_router
from kerf_imports.freecad import router as freecad_router
from kerf_imports.kicad import router as kicad_router
from kerf_imports.kicad_library import router as kicad_library_router
from kerf_imports.rhino3dm_route import router as rhino3dm_router
from kerf_render.routes import router as render_router

app = FastAPI()

app.include_router(fem.router, prefix="", tags=["fem"])
app.include_router(topo.router, prefix="", tags=["topo"])
if _tess_router is not None:
    app.include_router(_tess_router, prefix="", tags=["tess"])
app.include_router(cam.router, prefix="", tags=["cam"])
app.include_router(mates.router, prefix="", tags=["mates"])
app.include_router(bim_router, prefix="", tags=["bim"])
app.include_router(rf_router, prefix="", tags=["rf"])
app.include_router(spice_router, prefix="", tags=["spice"])
app.include_router(autoroute_router, prefix="", tags=["autoroute"])
app.include_router(pour_router, prefix="", tags=["pour"])
app.include_router(freecad_router, prefix="", tags=["import"])
app.include_router(kicad_router, prefix="", tags=["import"])
app.include_router(kicad_library_router, prefix="", tags=["import"])
app.include_router(rhino3dm_router, prefix="", tags=["rhino3dm"])
app.include_router(render_router, prefix="", tags=["render"])

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
