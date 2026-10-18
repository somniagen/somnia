from fastapi import Body

state = {"finished": 0}


def setup(ctx):
    state["finished"] = ctx.settings().get("finished", 0)

    @ctx.router.get("/stats")
    def stats():
        return state

    @ctx.router.post("/echo")
    def echo(body: dict = Body(...)):
        return {"you sent": body}

    def finished(job, drained):
        state["finished"] += 1
        ctx.save_settings({"finished": state["finished"]})
        ctx.broadcast("finished", state)

    ctx.on_job_finish(finished)


def teardown(ctx):
    ctx.log("bye")
