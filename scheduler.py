"""
PSX Trading Bot - Job Scheduler
Runs automated tasks during PSX market hours (9:30 AM - 3:30 PM PKT).
All results are served live via the dashboard — no Telegram/email alerts.
"""

from datetime import datetime
from loguru import logger

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logger.warning("APScheduler not installed")

from config import settings
from data_engine import data_engine
from ranking_engine import ranking_engine


class TradingScheduler:
    """Manage scheduled jobs for the trading bot."""

    def __init__(self):
        if SCHEDULER_AVAILABLE:
            self.scheduler = BackgroundScheduler(timezone=settings.TIMEZONE)
        else:
            self.scheduler = None
        self._is_running = False

    def job_premarket_fetch(self):
        """09:25 PKT - Fetch fresh data before market opens."""
        logger.info("PRE-MARKET: Fetching data for all KSE-100 stocks...")
        try:
            data_engine.fetch_all_kse100_data(force_refresh=True)
            logger.info("Pre-market data fetch complete")
        except Exception as e:
            logger.error(f"Pre-market fetch failed: {e}")

    def job_hourly_refresh(self):
        """Every hour while the server is running - refresh data and rerank."""
        logger.info("HOURLY REFRESH: Fetching fresh data and rerunning rankings...")
        try:
            data_engine.fetch_all_kse100_data(force_refresh=True)
            df = ranking_engine.rank_all()
            entry_count = len(df[df["signal"].isin(["BUY", "ACCUMULATE", "WATCH"])]) if not df.empty else 0
            exit_count = len(df[df["signal"].isin(["SELL", "TAKE_PROFIT", "OVERBOUGHT", "STOP_LOSS"])]) if not df.empty else 0
            logger.info(f"Hourly refresh complete: {entry_count} entry candidates, {exit_count} exit candidates")
        except Exception as e:
            logger.error(f"Hourly refresh failed: {e}")

    def job_market_open_analysis(self):
        """09:30 PKT - Run full ranking at market open."""
        logger.info("MARKET OPEN: Running full analysis...")
        try:
            df = ranking_engine.rank_all()
            logger.info(f"Market open analysis complete: {len(df)} stocks ranked")
        except Exception as e:
            logger.error(f"Market open analysis failed: {e}")

    def job_intraday_scan(self):
        """Every 30 min - Re-rank stocks with fresh data."""
        logger.info("INTRADAY SCAN: Re-ranking stocks...")
        try:
            df = ranking_engine.rank_all()
            entry_count = len(df[df["signal"].isin(["BUY", "ACCUMULATE", "WATCH"])]) if not df.empty else 0
            exit_count = len(df[df["signal"].isin(["SELL", "TAKE_PROFIT", "OVERBOUGHT", "STOP_LOSS"])]) if not df.empty else 0
            logger.info(f"Intraday scan complete: {entry_count} entry candidates, {exit_count} exit candidates")
        except Exception as e:
            logger.error(f"Intraday scan failed: {e}")

    def job_end_of_day_summary(self):
        """15:45 PKT - Final ranking of the day."""
        logger.info("END OF DAY: Final ranking...")
        try:
            df = ranking_engine.rank_all()
            summary = ranking_engine.generate_summary()
            logger.info("End-of-day ranking complete")
            logger.info(f"\n{summary}")
        except Exception as e:
            logger.error(f"EOD summary failed: {e}")

    def start(self):
        """Start the scheduler with all jobs configured."""
        if not SCHEDULER_AVAILABLE:
            logger.error("Cannot start scheduler: APScheduler not installed")
            return
        if self._is_running:
            logger.warning("Scheduler already running")
            return

        # Pre-market: Mon-Fri at 09:25 PKT
        self.scheduler.add_job(
            self.job_premarket_fetch,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=25),
            id="premarket_fetch", name="Pre-Market Data Fetch", replace_existing=True,
        )
        # Market open: Mon-Fri at 09:30 PKT
        self.scheduler.add_job(
            self.job_market_open_analysis,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=30),
            id="market_open", name="Market Open Analysis", replace_existing=True,
        )
        # Every hour while the server is running
        self.scheduler.add_job(
            self.job_hourly_refresh,
            IntervalTrigger(hours=1),
            id="hourly_refresh", name="Hourly Refresh", replace_existing=True,
        )
        # Intraday: Mon-Fri every 30 min 10:00-15:00 PKT
        self.scheduler.add_job(
            self.job_intraday_scan,
            CronTrigger(day_of_week="mon-fri", hour="10-14", minute="0,30"),
            id="intraday_scan", name="Intraday Signal Scan", replace_existing=True,
        )
        # End-of-day: Mon-Fri at 15:45 PKT
        self.scheduler.add_job(
            self.job_end_of_day_summary,
            CronTrigger(day_of_week="mon-fri", hour=15, minute=45),
            id="eod_summary", name="End-of-Day Summary", replace_existing=True,
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("Trading scheduler started with 5 jobs")
        self.list_jobs()

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler and self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Trading scheduler stopped")

    def list_jobs(self):
        """List all scheduled jobs."""
        if self.scheduler:
            for job in self.scheduler.get_jobs():
                logger.info(f"  Job: {job.name}: next run at {job.next_run_time}")

    @property
    def is_running(self) -> bool:
        return self._is_running


# Singleton
trading_scheduler = TradingScheduler()
