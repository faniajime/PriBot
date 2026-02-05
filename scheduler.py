from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def start_scheduler():
    if not scheduler.running:
        scheduler.start()

def schedule_job(reminder_id: int, run_date_utc, job_fn):
    scheduler.add_job(
        func=job_fn,
        trigger="date",
        run_date=run_date_utc,
        id=f"reminder_{reminder_id}",
        replace_existing=True,
        misfire_grace_time=60 * 5,
    )
