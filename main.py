import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from payme.errors import BasePaymeException
from payme import router
from payme.loader import db

app = FastAPI()
app.include_router(router.payme_router)
app.include_router(router.payment_router)


@app.exception_handler(BasePaymeException)
async def payme_exception_handler(request: Request, exc: BasePaymeException):
    return JSONResponse(exc.error, status_code=exc.status_code)


@app.on_event("startup")
async def startup():
    app.state.db = db
    await app.state.db.connect()
    logging.info("DB connected")


@app.on_event("shutdown")
async def shutdown():
    await app.state.db.pool.close()

    logging.info("DB disconnected")
